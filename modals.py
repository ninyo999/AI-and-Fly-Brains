import customtkinter as ctk
import openpyxl
from pathlib import Path
from arduino_ctrl import ArduinoHandler

class BaseModal(ctk.CTkToplevel):
    def __init__(self, parent, *args, **kwargs):
        super().__init__(parent, *args, **kwargs)
        self.attributes("-topmost", True)
        self.overrideredirect(True)
        self.wait_visibility()
        self.grab_set()  

    def close(self):
        self.grab_release()
        self.destroy()

class AddExpModal(BaseModal):
    def __init__(self, parent, save_callback, experiment_path_root):
        super().__init__(parent)
        self.arduino = ArduinoHandler()
        self.save_callback = save_callback
        self.exp_path_root = Path(experiment_path_root)
        self.geometry("900x650+230+80")
        self.configure(fg_color="#E5E5E5", corner_radius=30)
        
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=40, pady=20)
        ctk.CTkLabel(header, text="Add New Experiment", text_color="#B32442", 
                     font=ctk.CTkFont(size=32, weight="bold")).pack(side="left")
        ctk.CTkButton(header, text="X", width=40, height=40, corner_radius=20, 
                      fg_color="transparent", text_color="#B32442", border_width=2,
                      border_color="#B32442", command=self.close).pack(side="right")

        # Inputs
        self.title_e = self.create_input("Title:")
        self.drug_e = self.create_input("Drug use:")
        self.remark_e = self.create_textbox("Remark:")

        # LED Input Grids
        self.create_section("Dark field LEDs")
        df_frame = ctk.CTkFrame(self, fg_color="transparent")
        df_frame.pack(fill="x", padx=60)
        self.d_duty = self.create_grid_input(df_frame, "duty cycle", 0)
        self.d_freq = self.create_grid_input(df_frame, "frequency", 1)
        self.d_time = self.create_grid_input(df_frame, "active time", 2)

        self.create_section("Optogenetic LEDs")
        op_frame = ctk.CTkFrame(self, fg_color="transparent")
        op_frame.pack(fill="x", padx=60)
        self.o_duty = self.create_grid_input(op_frame, "duty cycle", 0)
        self.o_freq = self.create_grid_input(op_frame, "frequency", 1)
        self.o_len = self.create_grid_input(op_frame, "flash length", 2)
        self.o_delay = self.create_grid_input(op_frame, "initial delay", 3)

        ctk.CTkButton(self, text="Start Experiment", fg_color="#B32442", height=50, 
                      width=300, corner_radius=15, command=self.handle_start).pack(pady=30)

    def save_to_excel(self, folder_path):
        """Creates Excel with the requested template"""
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Experiment Details"

        # Template Data Mapping
        template_data = [
            ("Title:", self.title_e.get()),
            ("Drug use:", self.drug_e.get()),
            ("Remark:", self.remark_e.get("1.0", "end-1c")),
            ("", ""), # Blank Row 4
            ("Dark field LEDs", ""),
            ("duty cycle:", self.d_duty.get()),
            ("frequency:", self.d_freq.get()),
            ("active time:", self.d_time.get()),
            ("", ""), # Blank Row 9
            ("Optogenetic LEDs", ""),
            ("duty cycle:", self.o_duty.get()),
            ("frequency:", self.o_freq.get()),
            ("flash length:", self.o_len.get()),
            ("intial delay:", self.o_delay.get())
        ]

        for r_idx, (label, val) in enumerate(template_data, start=1):
            ws.cell(row=r_idx, column=1, value=label)
            ws.cell(row=r_idx, column=2, value=val)

        wb.save(folder_path / "experiment_data.xlsx")

    def handle_start(self):
        title = self.title_e.get()
        if title:
            new_dir = self.exp_path_root / title
            new_dir.mkdir(exist_ok=True)
            self.save_to_excel(new_dir)
            self.save_callback() # Refresh sidebar in gui.py
            self.close()

    def create_input(self, text):
        ctk.CTkLabel(self, text=text, text_color="#B32442", font=("Arial", 14, "bold")).pack(anchor="w", padx=60)
        e = ctk.CTkEntry(self, width=780, fg_color="white", border_width=0, text_color="black")
        e.pack(pady=(2, 10))
        return e

    def create_textbox(self, text):
        ctk.CTkLabel(self, text=text, text_color="#B32442", font=("Arial", 14, "bold")).pack(anchor="w", padx=60)
        t = ctk.CTkTextbox(self, width=780, height=100, fg_color="white", text_color="black")
        t.pack(pady=5)
        return t

    def create_section(self, text):
        ctk.CTkLabel(self, text=text, text_color="#E289A3", font=("Arial", 20, "bold")).pack(anchor="w", padx=60, pady=10)

    def create_grid_input(self, master, label, col):
        f = ctk.CTkFrame(master, fg_color="transparent")
        f.grid(row=0, column=col, padx=(0, 20))
        ctk.CTkLabel(f, text=label, text_color="#E289A3").pack(side="left")
        e = ctk.CTkEntry(f, width=80, fg_color="white", border_width=0, text_color="black")
        e.pack(side="left", padx=5)
        return e