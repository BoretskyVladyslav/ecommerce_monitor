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
        self.setup_context_menu()
        self.mainloop()

    def setup_context_menu(self):
        """Adds global right-click context menu for Copy/Paste."""
        import tkinter as tk
        
        # Create Menu
        self.context_menu = tk.Menu(self, tearoff=0)
        self.context_menu.add_command(label="Cut", command=lambda: self.focus_get().event_generate("<<Cut>>"))
        self.context_menu.add_command(label="Copy", command=lambda: self.focus_get().event_generate("<<Copy>>"))
        self.context_menu.add_command(label="Paste", command=lambda: self.focus_get().event_generate("<<Paste>>"))
        self.context_menu.add_separator()
        self.context_menu.add_command(label="Select All", command=lambda: self.focus_get().event_generate("<<SelectAll>>"))

        def show_menu(event):
            try:
                # Check if widget is an entry/text type
                widget = event.widget
                # Only show on relevant widgets (Entry, Text)
                if isinstance(widget, (tk.Entry, tk.Text)):
                    # Enable/Disable Paste based on clipboard
                    try:
                        self.clipboard_get()
                        state = "normal"
                    except:
                        state = "disabled"
                    self.context_menu.entryconfigure("Paste", state=state)

                    # Only enable Copy/Cut if text is selected
                    try:
                        if widget.selection_get():
                            self.context_menu.entryconfigure("Copy", state="normal")
                            self.context_menu.entryconfigure("Cut", state="normal")
                        else:
                            self.context_menu.entryconfigure("Copy", state="disabled")
                            self.context_menu.entryconfigure("Cut", state="disabled")
                    except:
                        self.context_menu.entryconfigure("Copy", state="disabled")
                        self.context_menu.entryconfigure("Cut", state="disabled")

                    self.context_menu.tk_popup(event.x_root, event.y_root)
            finally:
                self.context_menu.grab_release()

        # Global Bind to Right Click (Button-3 on Windows/Linux, Button-2 on Mac sometimes)
        self.bind_class("Text", "<Button-3>", show_menu)
        self.bind_class("Entry", "<Button-3>", show_menu)
