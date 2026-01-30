import customtkinter as ctk

class LoginWindow(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Manual Login")
        self.geometry("400x300")
