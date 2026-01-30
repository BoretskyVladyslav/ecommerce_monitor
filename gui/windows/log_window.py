import customtkinter as ctk
import datetime

class LogWindow(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.label = ctk.CTkLabel(self, text="System Logs", font=("Arial", 12, "bold"))
        self.label.pack(anchor="w", padx=5, pady=2)
        
        self.log_text = ctk.CTkTextbox(self, state="disabled")
        self.log_text.pack(fill="both", expand=True, padx=5, pady=5)
        
    def append_log(self, message):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        full_msg = f"[{timestamp}] {message}\n"
        
        self.log_text.configure(state="normal")
        self.log_text.insert("end", full_msg)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
