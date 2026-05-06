"""
track_annotate.py  —  YOLO + BoxMOT (StrongSORT) larval tracker
================================================================
Designed for:
  • 15–30 overlapping larvae per frame
  • Fixed 1 050-frame sequence at 30 fps (no new larvae mid-sequence)
  • macOS MPS (Apple Silicon) or CPU fallback
  • Strict re-ID: re-link lost tracks only within a ≤10-frame gap
  • 30-frame warm-up: stabilise IDs before locking them
  • Outputs:
      tracking_data.csv         – full per-detection log
      tracking_summary.csv      – per-larva coverage stats
      validity_check.png        – best-confidence annotated frame
      dlc_export/               – DeepLabCut-ready labelled-data folder
        frames/                 – extracted PNGs (one per tracked frame)
        CollectedData_scorer.csv – DLC multi-index CSV
        CollectedData_scorer.h5  – DLC HDF5 (same data, faster load)

Usage example (Mac terminal):
  python /Volumes/SSD512/larval_tracking_yolo/track_annotate.py \
    --images_dir  /Volumes/SSD512/larval_tracking_yolo/Exp_OPT_CsChr_20 \
    --model_path  /Volumes/SSD512/larval_tracking_yolo/best.pt \
    --output_dir  /Volumes/SSD512/larval_tracking_yolo/larval_outputE3 \
    --device mps \
    --img_size 640 \
    --preload_size 1280 \
    --no_annotated \
    --no_half \
    --scorer YourName
"""

import argparse
import csv
import shutil
import sys
import threading
import queue
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from tqdm import tqdm

# ── Dependency checks ─────────────────────────────────────────────────────────
try:
    from ultralytics import YOLO
except ImportError:
    sys.exit("pip install ultralytics")

# BoxMOT v17 moved StrongSort to an internal path.
# We try several known locations across versions so the script works on v10–v17.
_strongsort_cls = None
_boxmot_import_error = None
try:
    # v17 internal path
    from boxmot.trackers.strongsort.strong_sort import StrongSort as _SS
    _strongsort_cls = _SS
except ImportError:
    pass

if _strongsort_cls is None:
    try:
        # v10–v11 public export
        from boxmot import StrongSort as _SS          # noqa: F811
        _strongsort_cls = _SS
    except ImportError:
        pass

if _strongsort_cls is None:
    try:
        # v12–v16 tracker_zoo path
        from boxmot.trackers.tracker_zoo import create_tracker as _ct
        _strongsort_cls = None   # we'll use create_tracker instead
        _use_create_tracker = True
    except ImportError:
        _boxmot_import_error = True

if _boxmot_import_error:
    sys.exit("Cannot import StrongSort from boxmot. Run: pip install boxmot")

# Determine which instantiation path we have
_use_create_tracker = _strongsort_cls is None
if _use_create_tracker:
    from boxmot.trackers.tracker_zoo import create_tracker as _create_tracker   # noqa

# ── Single track colour ────────────────────────────────────────────────────────
# All detected larvae share one colour so annotations are visually clean.
# Change this tuple (BGR) to suit your background, e.g.:
#   cyan   (255, 255, 0)
#   yellow (0, 255, 255)
#   white  (255, 255, 255)
TRACK_COLOUR = (0, 255, 0)   # bright green (BGR)

WARMUP_FRAMES = 30   # frames used to stabilise initial IDs
MAX_GAP       = 50   # max frames a track may be absent before we stop re-linking


def get_colour(track_id: int) -> Tuple[int, int, int]:
    return TRACK_COLOUR


# ── Image I/O helpers ─────────────────────────────────────────────────────────

def sorted_image_paths(images_dir: str) -> List[Path]:
    exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}
    import re

    def _natural_key(p: Path):
        """Sort filenames by embedded numbers, so frame_2 < frame_10 < frame_100."""
        parts = re.split(r"(\d+)", p.stem)
        return [int(x) if x.isdigit() else x.lower() for x in parts]

    paths = sorted(
        [p for p in Path(images_dir).iterdir()
         if p.suffix.lower() in exts and not p.name.startswith("._")],
        key=_natural_key,
    )
    if not paths:
        sys.exit(f"No images found in: {images_dir}")
    return paths


def unc_safe_imread(path: Path) -> Optional[np.ndarray]:
    """Read image via numpy byte buffer (works on UNC / network paths)."""
    try:
        raw = np.fromfile(str(path), dtype=np.uint8)
        return cv2.imdecode(raw, cv2.IMREAD_COLOR)
    except Exception:
        return None


def ensure_bgr(img: np.ndarray) -> Optional[np.ndarray]:
    if img is None:
        return None
    if img.ndim == 2:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    if img.ndim == 3 and img.shape[2] == 1:
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    return img


def fast_load(path: Path, resize_to: int) -> Optional[np.ndarray]:
    img = unc_safe_imread(path)
    if img is None:
        return None
    img = ensure_bgr(img)
    if resize_to and (img.shape[0] > resize_to or img.shape[1] > resize_to):
        img = cv2.resize(img, (resize_to, resize_to), interpolation=cv2.INTER_AREA)
    return img


def image_loader_thread(paths: List[Path], resize_to: int, out_queue: queue.Queue):
    for path in paths:
        img = fast_load(path, resize_to)
        out_queue.put((path, img))
    out_queue.put(None)   # sentinel


def copy_to_local(src_paths: List[Path], local_dir: Path) -> List[Path]:
    local_dir.mkdir(parents=True, exist_ok=True)
    local_paths = []
    print(f"Copying {len(src_paths)} images to local disk: {local_dir}")
    for p in tqdm(src_paths, desc="Copying"):
        dest = local_dir / p.name
        if not dest.exists():
            shutil.copy2(str(p), str(dest))
        local_paths.append(dest)
    print()
    return local_paths


# ── Drawing helpers ───────────────────────────────────────────────────────────

def draw_track(frame: np.ndarray, x1: int, y1: int, x2: int, y2: int,
               track_id: int, conf: float) -> None:
    colour = get_colour(track_id)
    cv2.rectangle(frame, (x1, y1), (x2, y2), colour, 1)
    label = f"L{track_id} {conf:.2f}"
    (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.40, 1)
    cv2.rectangle(frame, (x1, y1 - th - 4), (x1 + tw + 4, y1), colour, -1)
    cv2.putText(frame, label, (x1 + 2, y1 - 3),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (0, 0, 0), 1, cv2.LINE_AA)


# ── IoU utility (for warm-up consensus matching) ──────────────────────────────

def iou(boxA: np.ndarray, boxB: np.ndarray) -> float:
    """Compute IoU between two [x1,y1,x2,y2] boxes."""
    xA = max(boxA[0], boxB[0]);  yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2]);  yB = min(boxA[3], boxB[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    if inter == 0:
        return 0.0
    aA = (boxA[2] - boxA[0]) * (boxA[3] - boxA[1])
    aB = (boxB[2] - boxB[0]) * (boxB[3] - boxB[1])
    return inter / float(aA + aB - inter)


# ── Warm-up: build stable initial ID mapping ──────────────────────────────────

def build_warmup_map(warmup_detections: List[List[Dict]]) -> Dict[int, int]:
    """
    Given detections for the first WARMUP_FRAMES frames (each detection has
    keys: track_id, x1, y1, x2, y2), cluster raw tracker IDs that consistently
    overlap (IoU > 0.4) into stable canonical IDs (1-based).

    Returns  {raw_tracker_id -> canonical_id}
    """
    # Collect all unique raw IDs seen during warmup
    raw_ids_seen: Dict[int, List[np.ndarray]] = defaultdict(list)
    for frame_dets in warmup_detections:
        for d in frame_dets:
            box = np.array([d["x1"], d["y1"], d["x2"], d["y2"]], dtype=float)
            raw_ids_seen[d["track_id"]].append(box)

    raw_ids = sorted(raw_ids_seen.keys())
    n = len(raw_ids)
    if n == 0:
        return {}

    # Build affinity matrix: two raw IDs are "same larva" if their median
    # boxes overlap strongly — helps in a dense overlapping scene.
    affinity = np.zeros((n, n), dtype=float)
    medians = {}
    for rid in raw_ids:
        boxes = np.array(raw_ids_seen[rid])
        medians[rid] = np.median(boxes, axis=0)

    for i, ri in enumerate(raw_ids):
        for j, rj in enumerate(raw_ids):
            if i == j:
                affinity[i, j] = 1.0
            else:
                affinity[i, j] = iou(medians[ri], medians[rj])

    # Union-Find: merge IDs whose median IoU > 0.40
    parent = {rid: rid for rid in raw_ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        parent[find(x)] = find(y)

    for i, ri in enumerate(raw_ids):
        for j, rj in enumerate(raw_ids):
            if i < j and affinity[i, j] > 0.40:
                union(ri, rj)

    # Assign canonical IDs (1-based, sorted by first-seen order)
    canonical_map: Dict[int, int] = {}
    root_to_canon: Dict[int, int] = {}
    canon_counter = 1
    for rid in raw_ids:
        root = find(rid)
        if root not in root_to_canon:
            root_to_canon[root] = canon_counter
            canon_counter += 1
        canonical_map[rid] = root_to_canon[root]

    return canonical_map


# ── Strict gap re-linker ──────────────────────────────────────────────────────

class GapRelinker:
    """
    After the warmup phase, if a canonical ID disappears then reappears within
    MAX_GAP frames, we re-link it.  New raw IDs that appear mid-sequence
    (impossible by design) are discarded.

    Internally maps  raw_id  →  canonical_id  using the warmup map, then
    extends it greedily for any new raw IDs produced by the tracker after
    warmup (tracker may internally reset an ID).
    """

    def __init__(self, canonical_map: Dict[int, int], max_gap: int = MAX_GAP):
        self.canonical_map = dict(canonical_map)  # raw_id -> canonical_id
        self.max_gap = max_gap

        # {canonical_id: last_seen_frame_idx}
        self.last_seen: Dict[int, int] = {}
        # {canonical_id: last known box [x1,y1,x2,y2]}
        self.last_box: Dict[int, np.ndarray] = {}

        # Set of all valid canonical IDs (locked after warmup)
        self.valid_canonical: set = set(canonical_map.values())

    def resolve(self, raw_id: int, box: np.ndarray,
                frame_idx: int) -> Optional[int]:
        """
        Returns the canonical ID for this detection, or None if it cannot be
        matched to any known larva (should never happen in a fixed-count sequence
        but handles tracker artefacts gracefully).
        """
        # Already mapped?
        if raw_id in self.canonical_map:
            cid = self.canonical_map[raw_id]
            self.last_seen[cid] = frame_idx
            self.last_box[cid] = box
            return cid

        # New raw ID — try to re-link to a recently-lost canonical ID
        best_cid = None
        best_score = -1.0
        for cid in self.valid_canonical:
            gap = frame_idx - self.last_seen.get(cid, -self.max_gap - 1)
            if gap < 1 or gap > self.max_gap:
                continue
            candidate_iou = iou(self.last_box.get(cid, np.zeros(4)), box)
            # Also factor in centroid distance (normalised)
            if cid in self.last_box:
                prev = self.last_box[cid]
                cx_prev = (prev[0] + prev[2]) / 2
                cy_prev = (prev[1] + prev[3]) / 2
                cx_cur  = (box[0]  + box[2])  / 2
                cy_cur  = (box[1]  + box[3])  / 2
                diag = np.hypot(box[2] - box[0], box[3] - box[1]) + 1e-6
                dist_norm = np.hypot(cx_cur - cx_prev, cy_cur - cy_prev) / diag
                score = candidate_iou * 0.6 + max(0, 1 - dist_norm) * 0.4
            else:
                score = candidate_iou
            if score > best_score and score > 0.2:
                best_score = score
                best_cid = cid

        if best_cid is not None:
            self.canonical_map[raw_id] = best_cid
            self.last_seen[best_cid] = frame_idx
            self.last_box[best_cid] = box
            return best_cid

        # Cannot link — return None (detection skipped in output)
        return None

    def update(self, cid: int, box: np.ndarray, frame_idx: int):
        self.last_seen[cid] = frame_idx
        self.last_box[cid] = box


# ── DeepLabCut export ─────────────────────────────────────────────────────────

def export_dlc(
    all_rows: List[Dict],
    image_paths_by_idx: Dict[int, Path],
    out_dir: Path,
    scorer: str,
) -> None:
    """
    Produce a DLC-compatible labeled-data folder:

      dlc_export/
        frames/                  ← PNG copies of every tracked frame
        CollectedData_<scorer>.csv
        CollectedData_<scorer>.h5

    Column structure follows DLC's multi-index convention:
      scorer / individual / bodypart / coords (x, y)

    Each larva is an 'individual'.  The single bodypart is 'centroid'.
    This is the minimal format DLC needs for multi-animal projects.
    If you want to refine keypoints, open the project in DLC GUI and
    use the existing frames + CSV as the starting point.
    """
    dlc_dir = out_dir / "dlc_export"
    frames_dir = dlc_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Collect all canonical IDs
    all_ids = sorted({r["track_id"] for r in all_rows})
    individuals = [f"larva{tid}" for tid in all_ids]
    bodypart = "centroid"

    # Build per-frame data dict
    frame_data: Dict[int, Dict[int, Tuple[float, float]]] = defaultdict(dict)
    for r in all_rows:
        frame_data[r["frame_idx"]][r["track_id"]] = (float(r["cx"]), float(r["cy"]))

    tracked_frames = sorted(frame_data.keys())

    # Build multi-index columns
    col_tuples = []
    for ind in individuals:
        col_tuples.append((scorer, ind, bodypart, "x"))
        col_tuples.append((scorer, ind, bodypart, "y"))
    col_index = pd.MultiIndex.from_tuples(
        col_tuples, names=["scorer", "individuals", "bodyparts", "coords"]
    )

    # Build row index — relative paths as DLC expects
    row_index = []
    rows = []
    for fi in tqdm(tracked_frames, desc="DLC export"):
        src_path = image_paths_by_idx.get(fi)
        if src_path is None:
            continue
        dest_name = f"img{fi:04d}.png"
        dest_path = frames_dir / dest_name
        if not dest_path.exists():
            img = fast_load(src_path, 0)  # no resize — DLC needs originals
            if img is not None:
                # PNG encoder requires 8-bit. Microscope TIFFs are often 16-bit
                # (dtype uint16). Normalise to 8-bit before saving.
                if img.dtype != np.uint8:
                    img_min, img_max = img.min(), img.max()
                    if img_max > img_min:
                        img = ((img.astype(np.float32) - img_min) /
                               (img_max - img_min) * 255).astype(np.uint8)
                    else:
                        img = img.astype(np.uint8)
                if not cv2.imwrite(str(dest_path), img):
                    tqdm.write(f"  [WARN] Failed to write PNG: {dest_path.name}")

        # DLC row index is relative to project labeled-data dir:
        # "labeled-data/<video_folder>/imgXXXX.png"
        row_index.append(f"labeled-data/frames/{dest_name}")

        row = []
        det = frame_data[fi]
        for tid in all_ids:
            if tid in det:
                row.extend([det[tid][0], det[tid][1]])
            else:
                row.extend([np.nan, np.nan])
        rows.append(row)

    df = pd.DataFrame(rows, index=row_index, columns=col_index)
    df.index.name = "bodyparts"   # DLC convention

    csv_path = dlc_dir / f"CollectedData_{scorer}.csv"
    h5_path  = dlc_dir / f"CollectedData_{scorer}.h5"

    df.to_csv(csv_path)

    # Write H5 with graceful fallback.
    # PyTables older versions cannot serialise a MultiIndex DataFrame in fixed
    # format — use format="table" which handles it correctly. If that also
    # fails (e.g. HDF5 library mismatch), skip H5 and warn: DLC can regenerate
    # it from the CSV with  dlc.convertcsv2h5(config, scorer).
    try:
        df.to_hdf(h5_path, key="df_with_missing", mode="w", format="table")
    except Exception as hdf_err:
        tqdm.write(
            f"  [WARN] Could not write H5 ({hdf_err.__class__.__name__}: {hdf_err}). "
            f"The CSV is complete — regenerate H5 inside DLC with:\n"
            f"    import deeplabcut; deeplabcut.convertcsv2h5(config, scorer='{scorer}')"
        )

    print(f"\n  DLC frames    : {frames_dir}  ({len(tracked_frames)} images)")
    print(f"  DLC CSV       : {csv_path}")
    print(f"  DLC H5        : {h5_path}")
    print(
        "\n  To use in DeepLabCut:\n"
        "  1. Create a multi-animal DLC project.\n"
        "  2. Copy dlc_export/frames/* into your project's\n"
        "     labeled-data/<video_name>/ folder.\n"
        "  3. Copy CollectedData_<scorer>.csv and .h5 into the same folder.\n"
        "  4. Run dlc.check_labels(config_path) to verify.\n"
        "  5. Run dlc.create_training_dataset(config_path) and train.\n"
    )


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run_pipeline(
    images_dir: str,
    model_path: str,
    output_dir: str,
    conf: float = 0.25,
    iou_thresh: float = 0.45,
    img_size: int = 640,
    preload_size: int = 1280,
    device: str = "mps",
    save_annotated: bool = True,
    half: bool = False,          # FP16 off by default on MPS
    local_cache: Optional[str] = None,
    scorer: str = "scorer",
) -> None:

    image_paths = sorted_image_paths(images_dir)
    total_frames = len(image_paths)

    if local_cache:
        cache_dir = Path(local_cache)
        image_paths = copy_to_local(image_paths, cache_dir)

    print(f"Found {total_frames} images")
    print(f"Device: {device}  |  FP16: {half}  |  img_size: {img_size}  "
          f"|  preload: {preload_size}px")
    print(f"Warm-up frames: {WARMUP_FRAMES}  |  Max re-link gap: {MAX_GAP} frames")
    print(f"Mode: {'all annotated frames' if save_annotated else 'validity_check + CSVs only'}\n")

    out_root = Path(output_dir)
    out_root.mkdir(parents=True, exist_ok=True)
    annotated_dir = out_root / "annotated"
    if save_annotated:
        annotated_dir.mkdir(parents=True, exist_ok=True)

    # ── Load YOLO ────────────────────────────────────────────────────────────
    print(f"Loading YOLO model: {model_path}")
    yolo = YOLO(model_path)

    # ── MPS image-size safety check ───────────────────────────────────────────
    # Apple MPS backend crashes silently (0 detections) when YOLO's internal
    # feature maps exceed 65 536 channels, which happens above ~1280px on MPS.
    MPS_MAX_IMGSZ = 1280
    if device == "mps" and img_size > MPS_MAX_IMGSZ:
        print(f"  [AUTO-FIX] --img_size {img_size} exceeds MPS limit. "
              f"Capping to {MPS_MAX_IMGSZ}px to avoid silent zero-detection bug.")
        img_size = MPS_MAX_IMGSZ

    # ── Build StrongSORT tracker ──────────────────────────────────────────────
    # StrongSORT is best for dense, overlapping, slow-moving objects.
    # max_age = MAX_GAP so lost tracks stay alive for re-linking.
    # n_init = 3 means a track must be seen 3× before being confirmed.
    #
    # Re-ID model runs on CPU even when YOLO is on MPS — StrongSORT's
    # osnet weights are not compiled for MPS.
    reid_device = "cpu"   # always CPU for the re-ID backbone on Mac
    reid_weights = Path("osnet_x0_25_msmt17.pt")   # auto-downloaded on first run

    if _use_create_tracker:
        # tracker_zoo path (BoxMOT v12–v16)
        tracker = _create_tracker(
            tracker_type="strongsort",
            tracker_config=None,
            reid_weights=reid_weights,
            device=reid_device,
            half=False,
        )
    else:
        # Direct class instantiation — try v17 signature first, fall back to v10
        import inspect as _inspect
        _init_params = set(_inspect.signature(_strongsort_cls.__init__).parameters)
        if "model_weights" in _init_params:
            # v10–v11 signature
            tracker = _strongsort_cls(
                model_weights=reid_weights,
                device=reid_device,
                fp16=False,
                max_age=MAX_GAP,
                n_init=3,
                nn_budget=100,
                mc_lambda=0.98,
                ema_alpha=0.9,
            )
        else:
            # v17 signature — uses reid_weights + device positionally
            tracker = _strongsort_cls(
                reid_weights=reid_weights,
                device=reid_device,
                half=False,
            )
            # v17 exposes max_age / n_init as attributes after init
            if hasattr(tracker, "max_age"):
                tracker.max_age = MAX_GAP
            if hasattr(tracker, "n_init"):
                tracker.n_init = 1

    # ── Background image loader ───────────────────────────────────────────────
    load_queue: queue.Queue = queue.Queue(maxsize=8)
    loader = threading.Thread(
        target=image_loader_thread,
        args=(image_paths, preload_size, load_queue),
        daemon=True,
    )
    loader.start()

    # Accumulators
    all_rows: List[Dict] = []
    larva_frames: Dict[int, List[int]] = defaultdict(list)
    image_paths_by_idx: Dict[int, Path] = {}

    # Warm-up buffer
    warmup_detections: List[List[Dict]] = []  # raw detections for first 30 frames
    warmup_frames_data: List[Tuple] = []      # (frame_idx, img_path, frame, raw_dets)

    # Best-confidence frame tracking
    best_frame_conf = -1.0
    best_frame_img: Optional[np.ndarray] = None

    relinker: Optional[GapRelinker] = None   # built after warmup

    print(f"\nTracking {total_frames} frames ...\n")
    pbar = tqdm(total=total_frames, desc="Frames")
    frame_idx = 0

    while True:
        item = load_queue.get()
        if item is None:
            break

        img_path, frame = item
        image_paths_by_idx[frame_idx] = img_path

        if frame is None:
            tqdm.write(f"  [WARN] Cannot read {img_path.name}")
            pbar.update(1)
            frame_idx += 1
            continue

        # ── YOLO detect (no built-in tracking — we drive BoxMOT manually) ────
        try:
            results = yolo.predict(
                frame,
                conf=conf,
                iou=iou_thresh,
                imgsz=img_size,
                device=device,
                half=half,
                verbose=False,
            )
        except Exception as e:
            tqdm.write(f"  [WARN] Frame {frame_idx}: {e}")
            pbar.update(1)
            frame_idx += 1
            continue

        # Build detection tensor for BoxMOT: [x1,y1,x2,y2,conf,cls]
        dets_np = np.empty((0, 6), dtype=np.float32)
        if results and results[0].boxes is not None and len(results[0].boxes):
            boxes_r = results[0].boxes
            xyxys  = boxes_r.xyxy.cpu().numpy()
            confs  = boxes_r.conf.cpu().numpy()
            clss   = boxes_r.cls.cpu().numpy()
            dets_np = np.column_stack([xyxys, confs, clss]).astype(np.float32)

        # ── BoxMOT update ─────────────────────────────────────────────────────
        # BoxMOT v17 signature: tracker.update(dets, img)
        # Returns array with columns: [x1, y1, x2, y2, track_id, conf, cls, det_idx]
        # Shape is (N, 8) when tracks exist, (0,) or (0,8) when empty.
        try:
            tracks = tracker.update(dets_np, frame)
        except TypeError:
            # Older BoxMOT versions that don't accept the image argument
            try:
                tracks = tracker.update(dets_np)
            except Exception as e2:
                tqdm.write(f"  [WARN] tracker.update failed frame {frame_idx}: {e2}")
                tracks = np.empty((0, 8))
        except Exception as e:
            tqdm.write(f"  [WARN] tracker.update error frame {frame_idx}: {e}")
            tracks = np.empty((0, 8))

        # Normalise: ensure tracks is always a 2D array
        if tracks is None or (hasattr(tracks, '__len__') and len(tracks) == 0):
            tracks = np.empty((0, 8))
        tracks = np.atleast_2d(tracks)

        # ── Collect raw detections for warm-up ───────────────────────────────
        frame_raw_dets: List[Dict] = []
        if tracks.shape[0] > 0 and tracks.shape[1] >= 6:
            for t in tracks:
                x1, y1, x2, y2 = int(t[0]), int(t[1]), int(t[2]), int(t[3])
                raw_tid  = int(t[4])
                det_conf = float(t[5])
                box_np   = np.array([x1, y1, x2, y2], dtype=float)
                frame_raw_dets.append({
                    "track_id": raw_tid,
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "conf": det_conf,
                    "box": box_np,
                })

        if frame_idx < WARMUP_FRAMES:
            # ── WARM-UP PHASE: buffer everything ─────────────────────────────
            warmup_detections.append(frame_raw_dets)
            warmup_frames_data.append((frame_idx, img_path, frame.copy(), frame_raw_dets))

        else:
            if relinker is None:
                # ── End of warm-up: build canonical ID map ────────────────────
                tqdm.write(f"\n  [INFO] Warm-up done. Building canonical ID map from "
                           f"{WARMUP_FRAMES} frames ...")
                canonical_map = build_warmup_map(warmup_detections)
                relinker = GapRelinker(canonical_map, max_gap=MAX_GAP)
                tqdm.write(f"  [INFO] Canonical larvae identified: "
                           f"{len(set(canonical_map.values()))}\n")

                # ── Replay buffered warm-up frames ───────────────────────────
                for wfi, wpath, wframe, wdets in warmup_frames_data:
                    frame_conf_sum = 0.0
                    n_det = 0
                    for d in wdets:
                        box_np = d["box"]
                        cid = relinker.resolve(d["track_id"], box_np, wfi)
                        if cid is None:
                            continue
                        x1, y1, x2, y2 = d["x1"], d["y1"], d["x2"], d["y2"]
                        draw_track(wframe, x1, y1, x2, y2, cid, d["conf"])
                        all_rows.append({
                            "frame_idx":    wfi,
                            "source_image": wpath.name,
                            "track_id":     cid,
                            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                            "cx": (x1 + x2) // 2,
                            "cy": (y1 + y2) // 2,
                            "width":  x2 - x1,
                            "height": y2 - y1,
                            "conf": round(d["conf"], 4),
                        })
                        larva_frames[cid].append(wfi)
                        frame_conf_sum += d["conf"]
                        n_det += 1

                    if n_det:
                        avg_conf = frame_conf_sum / n_det
                        if avg_conf > best_frame_conf:
                            best_frame_conf = avg_conf
                            best_frame_img = wframe.copy()

                    if save_annotated:
                        cv2.imwrite(
                            str(annotated_dir / f"frame_{wfi:04d}.png"), wframe
                        )
                warmup_frames_data.clear()

            # ── NORMAL PHASE: resolve + record ───────────────────────────────
            frame_conf_sum = 0.0
            n_det = 0
            annotated = frame.copy()

            for d in frame_raw_dets:
                box_np = d["box"]
                cid = relinker.resolve(d["track_id"], box_np, frame_idx)
                if cid is None:
                    continue
                x1, y1, x2, y2 = d["x1"], d["y1"], d["x2"], d["y2"]
                draw_track(annotated, x1, y1, x2, y2, cid, d["conf"])
                all_rows.append({
                    "frame_idx":    frame_idx,
                    "source_image": img_path.name,
                    "track_id":     cid,
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                    "cx": (x1 + x2) // 2,
                    "cy": (y1 + y2) // 2,
                    "width":  x2 - x1,
                    "height": y2 - y1,
                    "conf": round(d["conf"], 4),
                })
                larva_frames[cid].append(frame_idx)
                frame_conf_sum += d["conf"]
                n_det += 1

            if n_det:
                avg_conf = frame_conf_sum / n_det
                if avg_conf > best_frame_conf:
                    best_frame_conf = avg_conf
                    best_frame_img = annotated.copy()

            if save_annotated:
                cv2.imwrite(str(annotated_dir / f"frame_{frame_idx:04d}.png"), annotated)

        pbar.update(1)
        frame_idx += 1

    pbar.close()

    # ── Validity check image (highest average confidence frame) ───────────────
    validity_path = out_root / "validity_check.png"
    if best_frame_img is not None:
        cv2.imwrite(str(validity_path), best_frame_img)

    # ── CSVs ──────────────────────────────────────────────────────────────────
    tracking_csv = out_root / "tracking_data.csv"
    if all_rows:
        with open(tracking_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "frame_idx", "source_image", "track_id",
                "x1", "y1", "x2", "y2", "cx", "cy",
                "width", "height", "conf",
            ])
            writer.writeheader()
            writer.writerows(all_rows)

    summary_csv = out_root / "tracking_summary.csv"
    summary_rows = []
    for tid in sorted(larva_frames.keys()):
        frames = larva_frames[tid]
        summary_rows.append({
            "track_id":     tid,
            "total_frames": len(frames),
            "first_frame":  min(frames),
            "last_frame":   max(frames),
            "coverage_pct": round(100 * len(frames) / total_frames, 1),
        })
    if summary_rows:
        with open(summary_csv, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=summary_rows[0].keys())
            writer.writeheader()
            writer.writerows(summary_rows)

    # ── DeepLabCut export ─────────────────────────────────────────────────────
    if all_rows:
        export_dlc(all_rows, image_paths_by_idx, out_root, scorer)

    # ── Final report ──────────────────────────────────────────────────────────
    total_ids = len(larva_frames)
    print(f"\n{'='*58}")
    print(f"  Unique larvae tracked : {total_ids}")
    print(f"  Total detections      : {len(all_rows)}")
    if save_annotated:
        print(f"  Annotated frames      : {annotated_dir}")
    print(f"  Best-confidence frame : {validity_path}  (avg conf {best_frame_conf:.3f})")
    print(f"  Tracking CSV          : {tracking_csv}")
    print(f"  Summary CSV           : {summary_csv}")
    print(f"{'='*58}\n")

    print("Larvae coverage (canonical IDs):")
    for row in summary_rows:
        filled = int(row["coverage_pct"] / 2)
        bar = "#" * filled + "-" * (50 - filled)
        print(f"  Larva {row['track_id']:3d}  [{bar}]  "
              f"{row['coverage_pct']:5.1f}%  ({row['total_frames']} frames)")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "YOLO + BoxMOT (StrongSORT) larval tracker\n"
            "Fixed 1050-frame sequence, 15–30 overlapping larvae, 30 fps.\n"
            "\nExample (Mac terminal):\n"
            "  python track_annotate.py \\\n"
            "    --images_dir  /Volumes/SSD512/larval_tracking_yolo/Exp_OPT_CsChr_20 \\\n"
            "    --model_path  /Volumes/SSD512/larval_tracking_yolo/best.pt \\\n"
            "    --output_dir  /Volumes/SSD512/larval_tracking_yolo/larval_outputE3 \\\n"
            "    --device mps \\\n"
            "    --img_size 640 \\\n"
            "    --preload_size 1280 \\\n"
            "    --no_annotated \\\n"
            "    --no_half \\\n"
            "    --scorer YourName"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--images_dir",   required=True,
                   help="Folder containing input image sequence (sorted by name)")
    p.add_argument("--model_path",   required=True,
                   help="Path to YOLO best.pt weights")
    p.add_argument("--output_dir",   required=True,
                   help="Where to write all outputs")
    p.add_argument("--conf",         type=float, default=0.25,
                   help="YOLO detection confidence threshold (default 0.25)")
    p.add_argument("--iou",          type=float, default=0.45,
                   help="YOLO NMS IoU threshold (default 0.45)")
    p.add_argument("--img_size",     type=int,   default=640,
                   help="YOLO inference size in pixels (default 640)")
    p.add_argument("--preload_size", type=int,   default=1280,
                   help="Resize images to this before passing to YOLO (default 1280)")
    p.add_argument("--device",       default="mps",
                   help="Inference device: mps (Apple Silicon), cpu, 0 (CUDA). Default: mps")
    p.add_argument("--no_annotated", action="store_true",
                   help="Skip saving annotated frames; produce validity_check.png + CSVs only")
    p.add_argument("--no_half",      action="store_true",
                   help="Disable FP16 (required on MPS and CPU)")
    p.add_argument("--local_cache",  default=None,
                   help="Copy images here first (local SSD) to avoid slow network I/O")
    p.add_argument("--scorer",       default="scorer",
                   help="Your name/label for DeepLabCut CollectedData files (default: scorer)")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    run_pipeline(
        images_dir=args.images_dir,
        model_path=args.model_path,
        output_dir=args.output_dir,
        conf=args.conf,
        iou_thresh=args.iou,
        img_size=args.img_size,
        preload_size=args.preload_size,
        device=args.device,
        save_annotated=not args.no_annotated,
        half=not args.no_half,
        local_cache=args.local_cache,
        scorer=args.scorer,
    )