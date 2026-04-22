import os
import re
import shutil
import time
import customtkinter as ctk

from pathlib import Path
from tkinter import messagebox
from PIL import Image
from add_experiment_window import AddExpModal

# Paths
BASE_DIR = Path(__file__).parent
BG_IMAGE_PATH = BASE_DIR / "Icon/background.png"
EXP_DIR = BASE_DIR / "Experiment"
try:
    EXP_DIR.mkdir(exist_ok=True)
except OSError as e:
    print(f"Warning: could not create experiments directory: {e}")

_UNSAFE_CHARS = re.compile(r'[^\w\s\-.]')


def _load_image(path, fallback_size=(1, 1), fallback_color="#1E1E1E"):
    try:
        return Image.open(path)
    except (FileNotFoundError, OSError) as e:
        print(f"Warning: could not load image '{path}': {e}")
        return Image.new("RGB", fallback_size, color=fallback_color)


def _safe_folder_name(name):
    name = name.strip()
    name = _UNSAFE_CHARS.sub('', name)
    name = re.sub(r'\.\.+', '.', name)
    return name


class FlyBrainApp:
# ---- INIT ---------------------------------------------------------------------
    def __init__(self, root):
        self.root = root
        self.root.geometry("1366x768")
        self.root.title("AI and Fly Brains")

        # Background Image
        raw_bg = _load_image(BG_IMAGE_PATH, fallback_size=(1366, 768))
        self.bg_image = ctk.CTkImage(
            light_image=raw_bg,
            dark_image=raw_bg,
            size=(1366, 768)
        )
        self.bg_label = ctk.CTkLabel(self.root, image=self.bg_image, text="")
        self.bg_label.place(x=0, y=0)

        # Header Bar
        self.header = ctk.CTkFrame(self.root, height=45, fg_color="#FF0B55", corner_radius=0)
        self.header.place(x=0, y=0, relwidth=1)
        self.header_text = ctk.CTkLabel(
            self.header,
            text="AI and Fly brains - tools to study pain and aversive learning in fruit flies",
            font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
            text_color="#FFDEDE"
        )
        self.header_text.pack(pady=10)

        # Sidebar
        self.sidebar_width = 300
        self.sidebar_visible = True
        self.is_animating = False
        self.sidebar = ctk.CTkFrame(
            self.root,
            width=self.sidebar_width,
            fg_color="black",
            border_color="#FF0B55",
            border_width=2,
            corner_radius=0
        )
        self.sidebar.place(x=0, y=45, relheight=0.94)
        self.setup_sidebar()
# ---- INIT ---------------------------------------------------------------------

# ---- SIDEBAR ------------------------------------------------------------------
    def setup_sidebar(self):
        # Toggle Button
        sidebar_icon = _load_image(BASE_DIR / "Icon/sidebar.png", fallback_size=(20, 20))
        self.toggle_icon = ctk.CTkImage(
            light_image=sidebar_icon,
            dark_image=sidebar_icon,
            size=(20, 20)
        )
        self.toggle_btn = ctk.CTkButton(
            self.root,
            image=self.toggle_icon,
            text="",
            width=20,
            height=20,
            fg_color="black",
            hover_color="#1E1E1E",
            border_width=0,
            command=self.toggle_sidebar
        )
        self.toggle_btn.place(x=self.sidebar_width - 65, y=60)

        # View Experiment Title
        ctk.CTkLabel(
            self.sidebar,
            text="View Experiment",
            font=ctk.CTkFont(size=24, weight="bold"),
            text_color="white"
        ).pack(pady=15, anchor="nw", padx=20)

        # Search Bar
        self.search_container = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        self.search_container.pack(fill="x", padx=10, pady=5)

        self.search_entry = ctk.CTkEntry(
            self.search_container,
            placeholder_text="search experiment",
            fg_color="#FFDEDE",
            text_color="black",
            placeholder_text_color="#B32442",
            height=35,
            corner_radius=20
        )
        self.search_entry.pack(fill="x")

        self.clear_search_btn = ctk.CTkButton(
            self.search_entry,
            text="x",
            width=5,
            height=5,
            corner_radius=2,
            fg_color="transparent",
            text_color="#B32442",
            hover_color="#E289A3",
            command=self.clear_search
        )
        self.clear_search_btn.place(relx=0.95, rely=0.5, anchor="center")
        self.clear_search_btn.place_forget()
        self.search_entry.bind("<KeyRelease>", self.on_search_type)

        # Experiment List Container
        self.scroll_frame = ctk.CTkScrollableFrame(
            self.sidebar,
            fg_color="transparent",
            label_text=""
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=30, pady=5)

        # Add New Experiment Button
        self.add_btn = ctk.CTkButton(
            self.sidebar,
            text="+ Add new experiment",
            fg_color="#FFDEDE",
            text_color="black",
            hover_color="#E289A3",
            corner_radius=15,
            command=self.open_add_modal
        )
        self.add_btn.pack(side="bottom", pady=20, padx=20, fill="x")
        self.refresh_sidebar()

    def refresh_sidebar(self):
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()

        search_query = self.search_entry.get().lower()

        try:
            entries = os.listdir(EXP_DIR)
        except OSError as e:
            messagebox.showerror("Error", f"Could not read experiments directory:\n{e}")
            return

        folders = sorted([f for f in entries if os.path.isdir(EXP_DIR / f)])
        for folder in folders:
            if search_query and search_query not in folder.lower():
                continue
            row = ctk.CTkFrame(self.scroll_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)

            # Experiment List
            btn = ctk.CTkButton(
                row,
                text=f" {folder}",
                fg_color="#B32442",
                hover_color="#E289A3",
                text_color="white",
                anchor="w",
                height=30,
                corner_radius=15,
                command=lambda n=folder: print(f"Selected {n}")
            )
            btn.pack(side="left", fill="x", expand=True, padx=(0, 3))

            # Delete Experiment
            trash = ctk.CTkButton(
                row,
                text="x",
                width=30,
                height=40,
                fg_color="transparent",
                text_color="#FF0B55",
                hover_color="#1E1E1E",
                command=lambda n=folder: self.confirm_delete_modal(n)
            )
            trash.pack(side="right")

    def toggle_sidebar(self):
        if self.is_animating:
            return
        self.is_animating = True
        if self.sidebar_visible:
            self.animate_hide()
        else:
            self.animate_show()

    def animate_hide(self):
        for i in range(0, self.sidebar_width + 1, 15):
            self.sidebar.place(x=-i)
            new_x = max(10, (self.sidebar_width - 65) - i)
            self.toggle_btn.place(x=new_x)
            self.root.update()
            time.sleep(0.005)
        self.sidebar_visible = False
        self.is_animating = False

    def animate_show(self):
        for i in range(self.sidebar_width, -1, -15):
            self.sidebar.place(x=-i)
            self.toggle_btn.place(x=(self.sidebar_width - 65) - i)
            self.root.update()
            time.sleep(0.005)
        self.sidebar_visible = True
        self.is_animating = False

    def on_search_type(self, event):
        self.refresh_sidebar()
        if len(self.search_entry.get()) > 0:
            self.clear_search_btn.place(relx=0.93, rely=0.4, anchor="center")
        else:
            self.clear_search_btn.place_forget()

    def clear_search(self):
        self.search_entry.delete(0, 'end')
        self.clear_search_btn.place_forget()
        self.root.focus()
        self.refresh_sidebar()

# ---- SIDEBAR ------------------------------------------------------------------

    def open_add_modal(self):
        AddExpModal(self.root,
                    save_callback=self.refresh_sidebar,
                    experiment_path_root=EXP_DIR)

    def save_logic(self, name):
        name = _safe_folder_name(name)
        if not name:
            messagebox.showwarning("Invalid Name",
                                   "Experiment name cannot be empty or contain only special characters.")
            return
        try:
            (EXP_DIR / name).mkdir(exist_ok=True)
        except OSError as e:
            messagebox.showerror("Error", f"Could not create experiment folder:\n{e}")
            return
        self.refresh_sidebar()

    def confirm_delete_modal(self, folder_name):
        confirm_win = ctk.CTkToplevel(self.root)
        confirm_win.geometry("300x150+550+350")
        confirm_win.overrideredirect(True)
        confirm_win.configure(fg_color="#E5E5E5", corner_radius=60)
        confirm_win.attributes("-topmost", True)

        delete_dim = ctk.CTkToplevel(self.root)
        delete_dim.geometry(f"{self.root.winfo_width()}x{self.root.winfo_height()}+0+100")
        delete_dim.overrideredirect(True)
        delete_dim.configure(fg_color="black")
        delete_dim.attributes("-alpha", 0.6)

        header_frame = ctk.CTkFrame(confirm_win, fg_color="#B32442", height=60)
        header_frame.pack(fill="x", padx=2, pady=(2, 0))

        ctk.CTkLabel(
            header_frame,
            text="Confirm Deletion",
            text_color="white",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(pady=10)

        ctk.CTkLabel(
            confirm_win,
            text=f"Are you sure you want to remove\n'{folder_name}'?",
            text_color="#B32442",
            font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)

        btn_frame = ctk.CTkFrame(confirm_win, fg_color="transparent")
        btn_frame.pack(pady=10)

        def close_modal():
            if confirm_win.winfo_exists():
                confirm_win.destroy()
            if delete_dim.winfo_exists():
                delete_dim.destroy()

        def actual_delete():
            target = EXP_DIR / folder_name
            if not target.exists():
                messagebox.showwarning("Not Found", f"'{folder_name}' no longer exists.")
                close_modal()
                return
            try:
                shutil.rmtree(target)
            except OSError as e:
                messagebox.showerror("Delete Failed", f"Could not delete '{folder_name}':\n{e}")
                close_modal()
                return
            self.refresh_sidebar()
            close_modal()

        # Cancel Button
        ctk.CTkButton(
            btn_frame, text="cancel", fg_color="#B32442", text_color="white",
            width=80, corner_radius=15, command=close_modal
        ).pack(side="left", padx=10)

        # Delete Button
        ctk.CTkButton(
            btn_frame, text="delete", fg_color="white", text_color="#B32442",
            width=80, corner_radius=15, border_width=1, border_color="#B32442",
            hover_color="#FFDEDE", command=actual_delete
        ).pack(side="right", padx=10)


if __name__ == "__main__":
    app_root = ctk.CTk()
    app = FlyBrainApp(app_root)
    app_root.mainloop()
