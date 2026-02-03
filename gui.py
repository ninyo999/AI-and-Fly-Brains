import os
import time
import customtkinter as ctk
from pathlib import Path
from tkinter import PhotoImage, messagebox
from PIL import Image

# Paths
BASE_DIR = Path(__file__).parent
BG_IMAGE_PATH = BASE_DIR / "Icon/background.png"
EXP_DIR = BASE_DIR / "Experiment"
EXP_DIR.mkdir(exist_ok=True)

class FlyBrainApp:
# ---- INIT ---------------------------------------------------------------------
    def __init__(self, root):
        self.root = root
        self.root.geometry("1366x768")
        self.root.title("AI and Fly Brains")
        
        # Background Image 
        raw_bg = Image.open(BG_IMAGE_PATH)
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
            text="AI and Fly brains - tools to study pain and aversive learning in fruit flies 2025",
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
        sidebar_icon = Image.open(BASE_DIR / "Icon/sidebar.png")
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
            fg_color="transparent", 
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
        
        # Search Entry bind
        search_query = self.search_entry.get().lower()

        folders = sorted([f for f in os.listdir(EXP_DIR) if os.path.isdir(EXP_DIR / f)])
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
        if self.is_animating: return
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
        # Update the list
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

# ---- ADD EXPERIMENT -----------------------------------------------------------
    def open_add_modal(self):
        # Modal window
        modal = ctk.CTkToplevel(self.root)
        modal.geometry("600x600+350+100")
        modal.overrideredirect(True)
        modal.configure(fg_color="#E5E5E5", 
                        border_color="#B32442",
                        border_width=20,
                        corner_radius=2)
        modal.attributes("-topmost", True)
    
        self.dim = ctk.CTkToplevel(self.root)
        self.dim.geometry(f"{self.root.winfo_width()}x{self.root.winfo_height()}+0+70")
        self.dim.overrideredirect(True)
        self.dim.configure(fg_color="black")
        self.dim.attributes("-alpha", 0.5)

        ctk.CTkLabel(
            modal, 
            text="Add New Experiment", 
            text_color="#B32442", 
            font=ctk.CTkFont(size=26, weight="bold")
        ).pack(pady=20)

        # Helper for Inputs
        def create_input(label):
            ctk.CTkLabel(modal, text=label, text_color="#B32442", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=60)
            entry = ctk.CTkEntry(modal, width=500, fg_color="white", text_color="black", corner_radius=10, border_width=0)
            entry.pack(pady=(2, 15), ipady=5)
            return entry

        title_e = create_input("Title:")
        drug_e = create_input("Drug use:")
        
        ctk.CTkLabel(modal, text="Remark:", text_color="#B32442", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=60)
        remark_e = ctk.CTkTextbox(modal, width=500, height=100, fg_color="white", text_color="black", corner_radius=10)
        remark_e.pack(pady=5)

        # Start Button
        start_btn = ctk.CTkButton(
            modal, 
            text="Start Experiment", 
            fg_color="#B32442", 
            text_color="white",
            font=ctk.CTkFont(size=18, weight="bold"),
            height=45,
            width=250,
            corner_radius=25,
            command=lambda: self.save_and_close(title_e.get(), modal)
        )
        start_btn.pack(pady=30)

        def close():
            modal.destroy()
            self.dim.destroy()
        ctk.CTkButton(modal, text="Cancel", fg_color="transparent", text_color="gray", hover_color = "black" , command=close).pack()

    def save_and_close(self, name, modal):
        if name:
            (EXP_DIR / name).mkdir(exist_ok=True)
            self.refresh_sidebar()
            modal.destroy()
            self.dim.destroy()

    def confirm_delete_modal(self, folder_name):
        confirm_win = ctk.CTkToplevel(self.root)
        confirm_win.geometry("300x150+550+350") 
        confirm_win.overrideredirect(True)
        confirm_win.configure(fg_color="#E5E5E5", corner_radius=60)
        confirm_win.attributes("-topmost", True)

        self.delete_dim = ctk.CTkToplevel(self.root)
        self.delete_dim.geometry(f"{self.root.winfo_width()}x{self.root.winfo_height()}+0+100")
        self.delete_dim.overrideredirect(True)
        self.delete_dim.configure(fg_color="black")
        self.delete_dim.attributes("-alpha", 0.6)
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

        # Button Container
        btn_frame = ctk.CTkFrame(confirm_win, fg_color="transparent")
        btn_frame.pack(pady=10)

        def close_modal():
            confirm_win.destroy()
            self.delete_dim.destroy()

        def actual_delete():
            import shutil
            shutil.rmtree(EXP_DIR / folder_name)
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
        
# ---- ADD EXPERIMENT -----------------------------------------------------------

if __name__ == "__main__":
    app_root = ctk.CTk()
    app = FlyBrainApp(app_root)
    app_root.mainloop()