import customtkinter as ctk

class SettingsModal(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Settings")
        self.geometry("400x500")
        
        # Make modal
        self.transient(master)
        self.grab_set()
        
        self.grid_columnconfigure(1, weight=1)
        
        # Threads
        ctk.CTkLabel(self, text="Threads:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.entry_threads = ctk.CTkEntry(self)
        self.entry_threads.grid(row=0, column=1, padx=10, pady=10, sticky="ew")
        self.entry_threads.insert(0, "1")

        # Delay Min
        ctk.CTkLabel(self, text="Min Delay (sec):").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.entry_delay_min = ctk.CTkEntry(self)
        self.entry_delay_min.grid(row=1, column=1, padx=10, pady=10, sticky="ew")
        self.entry_delay_min.insert(0, "2")

        # Delay Max
        ctk.CTkLabel(self, text="Max Delay (sec):").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.entry_delay_max = ctk.CTkEntry(self)
        self.entry_delay_max.grid(row=2, column=1, padx=10, pady=10, sticky="ew")
        self.entry_delay_max.insert(0, "5")

        # Session Pause
        ctk.CTkLabel(self, text="Session Pause (sec):").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.entry_pause = ctk.CTkEntry(self)
        self.entry_pause.grid(row=3, column=1, padx=10, pady=10, sticky="ew")
        self.entry_pause.insert(0, "60")

        # Human Mode
        self.check_human = ctk.CTkCheckBox(self, text="Enable Human Mode (Deep Emulation)")
        self.check_human.grid(row=4, column=0, columnspan=2, padx=10, pady=20)

        # Save Button
        self.btn_save = ctk.CTkButton(self, text="Save Settings", command=self.on_save)
        self.btn_save.grid(row=5, column=0, columnspan=2, padx=10, pady=20)
        
        self.load_current_settings()

    def load_current_settings(self):
        # TODO: Load from Database
        pass

    def on_save(self):
        # TODO: Save to Database
        try:
            threads = int(self.entry_threads.get())
            d_min = int(self.entry_delay_min.get())
            d_max = int(self.entry_delay_max.get())
            pause = int(self.entry_pause.get())
            human = self.check_human.get()
            
            print(f"Saving Settings: Threads={threads}, Delay={d_min}-{d_max}, Pause={pause}, Human={human}")
            self.destroy()
        except ValueError:
            print("Invalid input values")
