"""
track_larval.py
===============
Two clean outputs from one run:

  1. ANNOTATED IMAGES  — every frame saved as a JPG with RGB bounding boxes,
                         track ID labels, and movement trails drawn on them.
                         Saved to:  output/annotated/

  2. DEEPLABCUT READY  — CollectedData CSV + original frames copied into the
                         correct DLC labeled-data folder structure.
                         Saved to:  output/deeplabcut/

Coordinate fix
--------------
Previous version had a coord scaling bug where cx/cy were multiplied ~2.75x
too large. This version reads the image at reduced scale for speed, runs YOLO,
then maps the detected box coordinates back to the ORIGINAL image pixel space
correctly using the actual decoded image dimensions.

Usage (from C: drive)
---------------------
  cd C:\\Users\\EEEE_4115_2025

  python track_larval.py ^
      --source \\\\tsclient\\SSD512\\larval_tracking_yolo\\Exp_OPT_CsChr_07_noATR\\ ^
      --weights best.pt ^
      --output C:\\Users\\EEEE_4115_2025\\Desktop\\larval_out ^
      --no-copy-frames

  # If images are NOT 5120x5120 (already small), use --read-scale 1.0
  # To keep only tracks seen in 10+ frames in DLC CSV: --min-frames 10
"""

import argparse
import colorsys
import csv
import math
import os
import queue
import re
import shutil
import sys
import tempfile
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# ── Redirect YOLO internal runs/ folder to temp — fixes Z: drive permission error
_YOLO_TMP = Path(tempfile.gettempdir()) / "yolo_runs"
_YOLO_TMP.mkdir(parents=True, exist_ok=True)
os.environ["YOLO_CONFIG_DIR"] = str(_YOLO_TMP)

import cv2
import numpy as np
from ultralytics import YOLO
from ultralytics.utils import SETTINGS
SETTINGS.update({"runs_dir": str(_YOLO_TMP)})


# ─────────────────────────────────────────────────────────────────────────────
# COLOUR  — unique vivid RGB per track ID, never repeats
# ─────────────────────────────────────────────────────────────────────────────
def get_colour(track_id: int) -> tuple:
    hue = (int(track_id) * 0.618033988749895) % 1.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.90, 1.0)
    return (int(b * 255), int(g * 255), int(r * 255))   # BGR for OpenCV


# ─────────────────────────────────────────────────────────────────────────────
# TRAIL MANAGER  — stores last N centroid positions per ID
# ─────────────────────────────────────────────────────────────────────────────
class TrailManager:
    def __init__(self, max_len: int = 50):
        self.trails  = defaultdict(list)
        self.max_len = max_len

    def update(self, tid: int, cx: int, cy: int):
        t = self.trails[tid]
        t.append((cx, cy))
        if len(t) > self.max_len:
            t.pop(0)

    def draw(self, frame: np.ndarray) -> np.ndarray:
        for tid, pts in self.trails.items():
            colour = get_colour(tid)
            for i in range(1, len(pts)):
                alpha = i / len(pts)
                cv2.line(frame, pts[i-1], pts[i], colour,
                         max(1, int(alpha * 3)), cv2.LINE_AA)
        return frame


# ─────────────────────────────────────────────────────────────────────────────
# ANNOTATE  — draw boxes, ID labels, trails, frame counter on a frame
# ─────────────────────────────────────────────────────────────────────────────
def annotate(frame: np.ndarray, boxes: np.ndarray, ids: np.ndarray,
             confs: np.ndarray, trails: TrailManager,
             frame_idx: int, total: int) -> np.ndarray:
    frame = trails.draw(frame)
    for box, tid, cf in zip(boxes, ids, confs):
        x1, y1, x2, y2 = map(int, box)
        cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
        col = get_colour(int(tid))
        cv2.rectangle(frame, (x1, y1), (x2, y2), col, 2, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), 5, col, -1, cv2.LINE_AA)
        lbl = f"ID {int(tid)}  {cf:.2f}"
        (tw, th), _ = cv2.getTextSize(lbl, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        cv2.rectangle(frame, (x1, y1 - th - 8), (x1 + tw + 4, y1), col, -1)
        cv2.putText(frame, lbl, (x1 + 2, y1 - 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA)
    txt = f"Frame {frame_idx+1}/{total}   Larvae: {len(ids)}"
    cv2.putText(frame, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (0, 0, 0), 4, cv2.LINE_AA)
    cv2.putText(frame, txt, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                0.8, (255, 255, 255), 2, cv2.LINE_AA)
    return frame


# ─────────────────────────────────────────────────────────────────────────────
# FRAME READER  — background thread decodes images while GPU runs inference
# ─────────────────────────────────────────────────────────────────────────────
class FrameReader:
    _FLAGS = {
        1.0:   cv2.IMREAD_COLOR,
        0.5:   cv2.IMREAD_REDUCED_COLOR_2,
        0.25:  cv2.IMREAD_REDUCED_COLOR_4,
        0.125: cv2.IMREAD_REDUCED_COLOR_8,
    }

    def __init__(self, paths: list, read_scale: float = 0.25,
                 infer_size: int = 640, queue_size: int = 16):
        self.paths      = paths
        self.read_scale = read_scale
        self.infer_size = infer_size
        self.flag       = self._FLAGS.get(read_scale, cv2.IMREAD_COLOR)
        self.q          = queue.Queue(maxsize=queue_size)
        self._t         = threading.Thread(target=self._worker, daemon=True)
        self._t.start()

    def _worker(self):
        for p in self.paths:
            img = cv2.imread(str(p), self.flag)
            if img is None:
                img = cv2.imread(str(p))
            if img is None:
                self.q.put(None)
                continue

            if len(img.shape) == 2 or img.shape[2] == 1:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)

            decoded_h, decoded_w = img.shape[:2]

            infer_img = cv2.resize(
                img, (self.infer_size, self.infer_size),
                interpolation=cv2.INTER_AREA)

            coord_scale_x = (decoded_w / self.infer_size) / self.read_scale
            coord_scale_y = (decoded_h / self.infer_size) / self.read_scale

            self.q.put((p.name, infer_img, img,
                        coord_scale_x, coord_scale_y))
        self.q.put(None)

    def __iter__(self):
        while True:
            item = self.q.get()
            if item is None:
                break
            yield item


# ─────────────────────────────────────────────────────────────────────────────
# DEEPLABCUT CSV WRITER
# ─────────────────────────────────────────────────────────────────────────────
def write_dlc_csv(records: list, source_name: str, dlc_dir: Path,
                  min_frames: int, scorer: str = "YOLOtracker",
                  bodypart: str = "centroid") -> Path | None:
    if not records:
        print("  WARNING: no detections — DLC CSV skipped.")
        return None

    import pandas as pd

    df        = pd.DataFrame(records)
    counts    = df.groupby("id")["frame"].nunique()
    valid_ids = counts[counts >= min_frames].index
    dropped   = len(counts) - len(valid_ids)
    if dropped:
        print(f"  DLC: dropped {dropped} short-lived IDs, "
              f"{len(valid_ids)} individuals kept.")
    df = df[df["id"].isin(valid_ids)].copy()
    if df.empty:
        print("  WARNING: all IDs filtered — lower --min-frames.")
        return None

    first_seen  = df.groupby("id")["frame"].min().sort_values().index.tolist()
    id_to_name  = {tid: f"larva_{i+1:03d}" for i, tid in enumerate(first_seen)}
    individuals = [id_to_name[tid] for tid in first_seen]

    all_fnames = (df.drop_duplicates("frame")
                    .sort_values("frame")["filename"].tolist())
    row_index  = [f"labeled-data/{source_name}/{fn}" for fn in all_fnames]

    col_tuples = []
    for ind in individuals:
        col_tuples.append((scorer, ind, bodypart, "x"))
        col_tuples.append((scorer, ind, bodypart, "y"))
    col_index = pd.MultiIndex.from_tuples(
        col_tuples, names=["scorer", "individuals", "bodyparts", "coords"])

    out       = pd.DataFrame(np.nan, index=row_index, columns=col_index)
    fn_to_row = {fn: f"labeled-data/{source_name}/{fn}" for fn in all_fnames}

    for _, row in df.iterrows():
        tid = row["id"]; fn = row["filename"]
        if tid not in id_to_name or fn not in fn_to_row:
            continue
        ind  = id_to_name[tid]
        ridx = fn_to_row[fn]
        out.at[ridx, (scorer, ind, bodypart, "x")] = row["cx"]
        out.at[ridx, (scorer, ind, bodypart, "y")] = row["cy"]

    lbl_dir  = dlc_dir / "labeled-data" / source_name
    lbl_dir.mkdir(parents=True, exist_ok=True)
    csv_path = lbl_dir / f"CollectedData_{scorer}.csv"
    out.to_csv(csv_path)

    filled  = out.notna().sum().sum() // 2
    total_c = len(individuals) * len(all_fnames)
    print(f"  DLC CSV → {csv_path.name}")
    print(f"           {len(individuals)} individuals | {len(all_fnames)} frames | "
          f"{filled:,}/{total_c:,} ({100*filled/total_c:.1f}% fill)")
    return csv_path


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def run_tracking(weights: str, source: str,
                 conf: float = 0.25, iou: float = 0.45, imgsz: int = 640,
                 trail_len: int = 50, min_frames: int = 5,
                 read_scale: float = 0.25, no_copy_frames: bool = False,
                 output_dir: str = None) -> None:

    if output_dir is None:
        output_dir = str(Path.home() / "Desktop" / "larval_output")
    out_dir      = Path(output_dir)
    annotated_dir = out_dir / "annotated"
    dlc_dir       = out_dir / "deeplabcut"
    try:
        annotated_dir.mkdir(parents=True, exist_ok=True)
        dlc_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        out_dir       = Path.home() / "Desktop" / "larval_output"
        annotated_dir = out_dir / "annotated"
        dlc_dir       = out_dir / "deeplabcut"
        annotated_dir.mkdir(parents=True, exist_ok=True)
        dlc_dir.mkdir(parents=True, exist_ok=True)
        print(f"WARNING: permission denied — writing to {out_dir} instead.")

    print(f"\nLoading model : {weights}")
    model = YOLO(weights)

    import torch
    use_fp16 = torch.cuda.is_available()
    device   = 0 if use_fp16 else "cpu"
    print(f"  Device      : {'GPU (FP16)' if use_fp16 else 'CPU'}")
    print(f"  Read scale  : {read_scale}  "
          f"({'5120→' + str(int(5120*read_scale)) + 'px' if read_scale < 1 else 'full res'})")

    source_path = Path(source)
    is_video    = source_path.suffix.lower() in {".mp4",".avi",".mov",".mkv"}
    source_name = source_path.stem

    if is_video:
        cap   = cv2.VideoCapture(str(source_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        def _vid():
            idx = 0
            while True:
                ok, f = cap.read()
                if not ok: break
                if len(f.shape) == 2 or f.shape[2] == 1:
                    f = cv2.cvtColor(f, cv2.COLOR_GRAY2BGR)
                h, w = f.shape[:2]
                small = cv2.resize(f, (imgsz, imgsz), interpolation=cv2.INTER_AREA)
                sx, sy = w / imgsz, h / imgsz
                yield (f"frame_{idx:05d}.jpg", small, f, sx, sy)
                idx += 1
        frame_iter  = _vid()
        frame_paths = None
    else:
        def _num_key(p):
            nums = re.findall(r"\d+", p.stem)
            return [int(n) for n in nums] if nums else [0]
        exts  = ("*.png","*.jpg","*.jpeg","*.tif","*.tiff","*.bmp")
        paths = []
        for e in exts:
            paths.extend(source_path.glob(e))
        paths       = sorted(paths, key=_num_key)
        total       = len(paths)
        frame_paths = paths
        frame_iter  = FrameReader(paths, read_scale=read_scale,
                                  infer_size=imgsz, queue_size=16)

    if total == 0:
        sys.exit(f"ERROR: no images found in {source_path.resolve()}")

    print(f"\nSource        : {source_path.resolve()}  ({total} frames)")
    print(f"Output        : {out_dir.resolve()}")
    print(f"Conf/IoU      : {conf}/{iou}   imgsz={imgsz}")
    print(f"DLC min-frames: {min_frames}\n")

    trails        = TrailManager(max_len=trail_len)
    all_records   = []
    track_history = {}
    t_start       = time.time()
    t_infer_total = 0.0

    for frame_idx, item in enumerate(frame_iter):
        if item is None:
            continue

        fname, infer_frame, display_frame, csx, csy = item

        t0 = time.time()
        results = model.track(
            source   = infer_frame,
            conf     = conf,
            iou      = iou,
            imgsz    = imgsz,
            tracker  = "bytetrack.yaml",
            persist  = True,
            verbose  = False,
            save     = False,
            half     = use_fp16,
            device   = device,
            project  = str(_YOLO_TMP),
            exist_ok = True,
        )
        t_infer_total += time.time() - t0

        elapsed  = time.time() - t_start
        fps_live = (frame_idx + 1) / elapsed
        eta_s    = (total - frame_idx - 1) / fps_live if fps_live > 0 else 0
        print(f"  [{frame_idx+1:04d}/{total}]  "
              f"{(time.time()-t0)*1000:.0f}ms  "
              f"{fps_live:.1f}fps  "
              f"ETA {int(eta_s//60)}m{int(eta_s%60):02d}s     ",
              end="\r")

        res         = results[0]
        boxes_infer = res.boxes.xyxy.cpu().numpy() \
                      if res.boxes is not None else np.empty((0, 4))
        ids_np      = res.boxes.id.cpu().numpy().astype(int) \
                      if (res.boxes is not None and res.boxes.id is not None) \
                      else np.array([], dtype=int)
        confs_np    = res.boxes.conf.cpu().numpy() \
                      if res.boxes is not None else np.empty((0,))

        boxes_orig = np.zeros_like(boxes_infer)
        if len(boxes_infer):
            boxes_orig[:, 0] = boxes_infer[:, 0] * csx
            boxes_orig[:, 1] = boxes_infer[:, 1] * csy
            boxes_orig[:, 2] = boxes_infer[:, 2] * csx
            boxes_orig[:, 3] = boxes_infer[:, 3] * csy

        dh, dw = display_frame.shape[:2]
        scale_disp_x = dw / imgsz
        scale_disp_y = dh / imgsz
        boxes_disp = np.zeros_like(boxes_infer)
        if len(boxes_infer):
            boxes_disp[:, 0] = boxes_infer[:, 0] * scale_disp_x
            boxes_disp[:, 1] = boxes_infer[:, 1] * scale_disp_y
            boxes_disp[:, 2] = boxes_infer[:, 2] * scale_disp_x
            boxes_disp[:, 3] = boxes_infer[:, 3] * scale_disp_y

        for box_d, tid in zip(boxes_disp, ids_np):
            trails.update(int(tid),
                          int((box_d[0] + box_d[2]) / 2),
                          int((box_d[1] + box_d[3]) / 2))

        for box_o, tid, cf in zip(boxes_orig, ids_np, confs_np):
            x1, y1, x2, y2 = box_o
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            all_records.append({
                "frame"   : frame_idx,
                "filename": fname,
                "id"      : int(tid),
                "cx"      : round(float(cx), 2),
                "cy"      : round(float(cy), 2),
                "x1"      : round(float(x1), 2),
                "y1"      : round(float(y1), 2),
                "x2"      : round(float(x2), 2),
                "y2"      : round(float(y2), 2),
                "conf"    : round(float(cf), 4),
            })
            if tid not in track_history:
                track_history[tid] = dict(
                    first_frame=frame_idx, last_frame=frame_idx,
                    prev_cx=cx, prev_cy=cy,
                    total_dist=0.0, det_count=0)
            th = track_history[tid]
            th["last_frame"]  = frame_idx
            th["total_dist"] += math.hypot(cx - th["prev_cx"],
                                           cy - th["prev_cy"])
            th["prev_cx"], th["prev_cy"] = cx, cy
            th["det_count"] += 1

        ann = annotate(display_frame.copy(), boxes_disp, ids_np, confs_np,
                       trails, frame_idx, total)
        out_fname = Path(fname).stem + ".jpg"
        cv2.imwrite(str(annotated_dir / out_fname), ann,
                    [cv2.IMWRITE_JPEG_QUALITY, 92])

    if is_video:
        cap.release()

    elapsed = time.time() - t_start
    print(f"\n\nDone — {total} frames in {elapsed/60:.1f} min  "
          f"({total/elapsed:.1f} fps avg, "
          f"{t_infer_total/max(total,1)*1000:.0f}ms infer/frame avg)\n")

    _write_tracks_csv(all_records,    out_dir / "tracks.csv")
    _write_summary_csv(track_history, out_dir / "summary.csv")

    print("\nBuilding DeepLabCut CSV...")
    dlc_csv = write_dlc_csv(all_records, source_name, dlc_dir, min_frames)

    if frame_paths and dlc_csv and not no_copy_frames:
        lbl_dir = dlc_dir / "labeled-data" / source_name
        to_copy = [(p, lbl_dir / p.name) for p in frame_paths
                   if not (lbl_dir / p.name).exists()]
        if to_copy:
            print(f"  Copying {len(to_copy)} original frames → DLC folder "
                  f"(8 threads)...")
            with ThreadPoolExecutor(max_workers=8) as ex:
                ex.map(lambda a: shutil.copy(a[0], a[1]), to_copy)
    elif no_copy_frames:
        print(f"  Frame copy skipped (--no-copy-frames).")
        print(f"  Point DLC at your original folder: {source_path.resolve()}")

    n_ann = len(list(annotated_dir.glob("*.jpg")))
    print(f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Outputs → {out_dir.resolve()}

  OUTPUT 1 — Annotated images ({n_ann} files)
    annotated/
      frame_00000.jpg
      frame_00001.jpg
      ...

  OUTPUT 2 — DeepLabCut ready
    tracks.csv
    summary.csv
    deeplabcut/
      labeled-data/{source_name}/
        CollectedData_YOLOtracker.csv
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
""")


# ─────────────────────────────────────────────────────────────────────────────
# CSV HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def _write_tracks_csv(records: list, path: Path):
    if not records: return
    fields = ["frame","filename","id","cx","cy","x1","y1","x2","y2","conf"]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(records)
    print(f"  tracks.csv   — {len(records):,} detections")

def _write_summary_csv(track_history: dict, path: Path):
    rows = [{"id": tid,
             "first_frame"  : th["first_frame"],
             "last_frame"   : th["last_frame"],
             "frames_seen"  : th["det_count"],
             "total_dist_px": round(th["total_dist"], 2)}
            for tid, th in sorted(track_history.items())]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["id","first_frame","last_frame",
                                           "frames_seen","total_dist_px"])
        w.writeheader()
        w.writerows(rows)
    print(f"  summary.csv  — {len(rows)} unique IDs")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    p = argparse.ArgumentParser(
        description="Larval tracking → annotated images + DeepLabCut CSV")
    p.add_argument("--source",         required=True)
    p.add_argument("--weights",        default="best.pt")
    p.add_argument("--conf",           type=float, default=0.25)
    p.add_argument("--iou",            type=float, default=0.45)
    p.add_argument("--imgsz",          type=int,   default=640)
    p.add_argument("--trail-len",      type=int,   default=50)
    p.add_argument("--min-frames",     type=int,   default=5)
    p.add_argument("--read-scale",     type=float, default=0.25)
    p.add_argument("--no-copy-frames", action="store_true")
    p.add_argument("--output",         default=None)
    args = p.parse_args()

    run_tracking(
        weights        = args.weights,
        source         = args.source,
        conf           = args.conf,
        iou            = args.iou,
        imgsz          = args.imgsz,
        trail_len      = args.trail_len,
        min_frames     = args.min_frames,
        read_scale     = args.read_scale,
        no_copy_frames = args.no_copy_frames,
        output_dir     = args.output,
    )
