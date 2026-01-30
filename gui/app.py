import customtkinter as ctk

class Application(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Ecommerce Monitor")
        self.geometry("1000x800")
        
        # Grid configuration
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        from gui.windows.main_window import MainWindow
        self.main_window = MainWindow(self)
        self.main_window.grid(row=0, column=0, sticky="nsew")
        
    def run(self):
        self.mainloop()
