import customtkinter as ctk
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
    def __init__(self, parent, save_callback):
        super().__init__(parent)
        self.arduino = ArduinoHandler()
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

        # Inputs (Title, Drug, Remark)
        self.title_e = self.create_input("Title:")
        self.drug_e = self.create_input("Drug use:")
        self.remark_e = self.create_textbox("Remark:")

        # LED Settings Grid
        self.create_section("Dark field LEDs")
        dark_f = ctk.CTkFrame(self, fg_color="transparent")
        dark_f.pack(fill="x", padx=60)
        self.d_duty = self.create_grid_input(dark_f, "duty cycle", 0)
        self.d_freq = self.create_grid_input(dark_f, "frequency", 1)
        self.d_time = self.create_grid_input(dark_f, "active time", 2)

        self.create_section("Optogenetic LEDs")
        opto_f = ctk.CTkFrame(self, fg_color="transparent")
        opto_f.pack(fill="x", padx=60)
        self.o_duty = self.create_grid_input(opto_f, "duty cycle", 0)
        self.o_freq = self.create_grid_input(opto_f, "frequency", 1)
        self.o_len = self.create_grid_input(opto_f, "flash length", 2)
        self.o_delay = self.create_grid_input(opto_f, "initial delay", 3)

        ctk.CTkButton(self, text="Start Experiment", fg_color="#B32442", height=50, 
                      width=300, corner_radius=15, command=lambda: self.start(save_callback)).pack(pady=30)

    def start(self, callback):
        data = {"dark_duty": self.d_duty.get(), "dark_freq": self.d_freq.get(), "dark_time": self.d_time.get(),
                "opto_duty": self.o_duty.get(), "opto_freq": self.o_freq.get(), "opto_len": self.o_len.get(), "opto_delay": self.o_delay.get()}
        self.arduino.send_led_data(data)
        callback(self.title_e.get())
        self.close()

    def create_input(self, text):
        ctk.CTkLabel(self, text=text, text_color="#B32442", font=("Arial", 14, "bold")).pack(anchor="w", padx=60)
        e = ctk.CTkEntry(self, width=780, fg_color="white", border_width=0)
        e.pack(pady=(2, 10))
        return e

    def create_textbox(self, text):
        ctk.CTkLabel(self, text=text, text_color="#B32442", font=("Arial", 14, "bold")).pack(anchor="w", padx=60)
        t = ctk.CTkTextbox(self, width=780, height=100, fg_color="white")
        t.pack(pady=5)
        return t

    def create_section(self, text):
        ctk.CTkLabel(self, text=text, text_color="#E289A3", font=("Arial", 20, "bold")).pack(anchor="w", padx=60, pady=10)

    def create_grid_input(self, master, label, col):
        f = ctk.CTkFrame(master, fg_color="transparent")
        f.grid(row=0, column=col, padx=(0, 20))
        ctk.CTkLabel(f, text=label, text_color="#E289A3").pack(side="left")
        e = ctk.CTkEntry(f, width=80, fg_color="white", border_width=0)
        e.pack(side="left", padx=5)
        return e