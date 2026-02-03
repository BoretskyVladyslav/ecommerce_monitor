import customtkinter as ctk

class DbConfigModal(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Database Configuration")
        self.geometry("400x300")
        self.resizable(False, False)
        
        # Center the window
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")
        
        self.grab_set() # Make modal
        
        # --- Form ---
        self.frame = ctk.CTkFrame(self)
        self.frame.pack(fill="both", expand=True, padx=20, pady=20)
        
        # Host
        ctk.CTkLabel(self.frame, text="Host:").pack(anchor="w", pady=(10, 0))
        self.entry_host = ctk.CTkEntry(self.frame, placeholder_text="localhost")
        self.entry_host.pack(fill="x", pady=(0, 10))
        
        # User
        ctk.CTkLabel(self.frame, text="User:").pack(anchor="w")
        self.entry_user = ctk.CTkEntry(self.frame, placeholder_text="root")
        self.entry_user.pack(fill="x", pady=(0, 10))
        
        # Password
        ctk.CTkLabel(self.frame, text="Password:").pack(anchor="w")
        self.entry_pass = ctk.CTkEntry(self.frame, show="*")
        self.entry_pass.pack(fill="x", pady=(0, 20))
        
        # Save Button
        self.btn_save = ctk.CTkButton(self.frame, text="Save Config", command=self.on_save)
        self.btn_save.pack(fill="x", pady=10)
        
    def on_save(self):
        # Placeholder for save logic
        print(f"DB Config Saved: {self.entry_host.get()} / {self.entry_user.get()}")
        self.destroy()
