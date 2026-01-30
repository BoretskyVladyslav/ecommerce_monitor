import customtkinter as ctk

class MainWindow(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # --- Layout Configuration ---
        self.grid_rowconfigure(1, weight=1) # Table area takes remaining space
        self.grid_columnconfigure(0, weight=1)

        # --- Top Control Panel (Start/Stop) ---
        self.control_panel = ctk.CTkFrame(self)
        self.control_panel.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        
        self.btn_start = ctk.CTkButton(self.control_panel, text="Start Monitoring", fg_color="green", command=self.on_start)
        self.btn_start.pack(side="left", padx=5, pady=5)
        
        self.btn_pause = ctk.CTkButton(self.control_panel, text="Pause", fg_color="orange", command=self.on_pause)
        self.btn_pause.pack(side="left", padx=5, pady=5)
        
        self.btn_stop = ctk.CTkButton(self.control_panel, text="Stop", fg_color="red", command=self.on_stop)
        self.btn_stop.pack(side="left", padx=5, pady=5)

        self.btn_settings = ctk.CTkButton(self.control_panel, text="Settings", command=self.on_settings)
        self.btn_settings.pack(side="right", padx=5, pady=5)

        # --- Sessions Table Area ---
        self.table_frame = ctk.CTkFrame(self)
        self.table_frame.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.table_frame.grid_rowconfigure(1, weight=1)
        self.table_frame.grid_columnconfigure(0, weight=1)

        # Headers
        self.header_frame = ctk.CTkFrame(self.table_frame, height=30)
        self.header_frame.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        headers = ["ID", "Name", "Type", "Proxy", "Status", "Note"]
        weights = [0, 1, 1, 2, 1, 2] # Relative width weights
        
        for i, header in enumerate(headers):
            self.header_frame.grid_columnconfigure(i, weight=weights[i])
            lbl = ctk.CTkLabel(self.header_frame, text=header, font=("Arial", 12, "bold"))
            lbl.grid(row=0, column=i, sticky="ew", padx=5)

        # Scrollable list for rows
        self.scroll_frame = ctk.CTkScrollableFrame(self.table_frame)
        self.scroll_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.scroll_frame.grid_columnconfigure(0, weight=1) # Ensure rows stretch

        # --- Bottom Action Panel (Add/Edit/Delete/Login) ---
        self.action_panel = ctk.CTkFrame(self)
        self.action_panel.grid(row=2, column=0, sticky="ew", padx=10, pady=10)

        self.btn_add = ctk.CTkButton(self.action_panel, text="Add Session", command=self.on_add)
        self.btn_add.pack(side="left", padx=5, pady=5)

        self.btn_edit = ctk.CTkButton(self.action_panel, text="Edit Session", command=self.on_edit)
        self.btn_edit.pack(side="left", padx=5, pady=5)

        self.btn_delete = ctk.CTkButton(self.action_panel, text="Delete", fg_color="darkred", command=self.on_delete)
        self.btn_delete.pack(side="left", padx=5, pady=5)
        
        self.btn_login = ctk.CTkButton(self.action_panel, text="Login (Browser)", command=self.on_login)
        self.btn_login.pack(side="right", padx=5, pady=5)
        
        # --- Log Window ---
        from gui.windows.log_window import LogWindow
        self.log_window = LogWindow(self, height=150)
        self.log_window.grid(row=3, column=0, sticky="ew", padx=10, pady=5)
        
        
        # Data storage
        self.sessions_data = {}
        self.selected_session_id = None
        self.row_widgets = {} # id -> list of widgets to update color

        # Load Real Data from DB
        self.reload_sessions_from_db()

    def reload_sessions_from_db(self):
        import threading
        import asyncio
        from database.db_manager import DatabaseManager
        
        def fetch_task():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            db = DatabaseManager()
            try:
                # Force fresh pool if needed by ensuring previous was closed
                # But DatabaseManager is singleton. 
                # If _pool points to closed loop object, it might fail.
                # Ideally check _pool.loop.is_closed().
                # For now assume main.py closed it.
                
                query = "SELECT * FROM sessions"
                sessions = loop.run_until_complete(db.fetch_all(query))
                loop.run_until_complete(db.close())
            except Exception as e:
                print(f"DB Fetch Error: {e}")
                sessions = []
            finally:
                loop.close()
            
            self.after(0, lambda: self.render_sessions(sessions))

        threading.Thread(target=fetch_task, daemon=True).start()

    def render_sessions(self, sessions):
        # Clear existing rows? For now just add, assuming called once on init.
        # Ideally clear self.scroll_frame children first if refreshing.
        for widget in self.scroll_frame.winfo_children():
            widget.destroy()
        self.sessions_data = {}
        self.row_widgets = {}

        for s in sessions:
            # Handle None values if any
            proxy = s.get('proxy') or ""
            # Hide credentials for display if desired, or show full. User allowed full.
            
            self.add_session_row(
                s_id=s['id'],
                name=s['name'],
                s_type=s['type'],
                proxy=proxy,
                status=s.get('status', 'Ready'),
                note="Loaded from DB"
            )
            # Update correct data from DB
            self.sessions_data[s['id']]['user_agent'] = s.get('user_agent')
            self.sessions_data[s['id']]['cookies_path'] = s.get('cookies_path') or f"sessions/{s['id']}_cookies.json"

    def add_session_row(self, s_id, name, s_type, proxy, status, note):
        # Store data for logic usage
        self.sessions_data[s_id] = {
            "id": s_id, "name": name, "type": s_type, 
            "proxy": proxy, "status": status, 
            "cookies_path": f"sessions/{s_id}_cookies.json", 
            "user_agent": "Mozilla/5.0... (Placeholder)" # Should fetch real UA if in DB
            # TODO: Fetch UA from DB column
        }
        
        # If user_agent in DB row, use it
        # The fetch_task returns dicts with all columns
        # We need to pass the full row data to add_session_row or handle it there.
        # Let's fix sessions_data population in render_sessions loop or here.
        
        # Wait, I am inside add_session_row. I don't have the full row here unless I pass it.
        # Let's patch: add_session_row is used by render_sessions.
        # I should probably update sessions_data AFTER checking DB row.
        # But for UI consistency, let's keep add_session_row focused on UI.
        
        row_frame = ctk.CTkFrame(self.scroll_frame)
        row_frame.pack(fill="x", pady=2)
        
        weights = [0, 1, 1, 2, 1, 2]
        for i, w in enumerate(weights):
            row_frame.grid_columnconfigure(i, weight=w)
            
        colors = {"Ready": "green", "Error": "red", "Wait": "orange", "Run": "blue"}
        status_color = colors.get(status, "gray")

        # Create widgets
        widgets = []
        w1 = ctk.CTkLabel(row_frame, text=str(s_id))
        w1.grid(row=0, column=0, padx=5, pady=5)
        widgets.append(w1)
        
        w2 = ctk.CTkLabel(row_frame, text=name)
        w2.grid(row=0, column=1, padx=5, pady=5)
        widgets.append(w2)
        
        w3 = ctk.CTkLabel(row_frame, text=s_type)
        w3.grid(row=0, column=2, padx=5, pady=5)
        widgets.append(w3)
        
        # Truncate proxy for display
        display_proxy = proxy
        if len(display_proxy) > 30:
            display_proxy = display_proxy[:27] + "..."
        if not proxy: display_proxy = "Direct"

        w4 = ctk.CTkLabel(row_frame, text=display_proxy)
        w4.grid(row=0, column=3, padx=5, pady=5)
        widgets.append(w4)
        
        status_lbl = ctk.CTkLabel(row_frame, text=status, text_color=status_color, font=("Arial", 12, "bold"))
        status_lbl.grid(row=0, column=4, padx=5, pady=5)
        widgets.append(status_lbl)
        
        w5 = ctk.CTkLabel(row_frame, text=note)
        w5.grid(row=0, column=5, padx=5, pady=5)
        widgets.append(w5)
        
        self.row_widgets[s_id] = [row_frame] + widgets

        # Bind click events for selection
        def on_click(event):
            self.select_session(s_id)
            
        row_frame.bind("<Button-1>", on_click)
        for w in widgets:
            w.bind("<Button-1>", on_click)

    def select_session(self, s_id):
        # Reset previous selection style if needed
        if self.selected_session_id and self.selected_session_id in self.row_widgets:
            prev_frame = self.row_widgets[self.selected_session_id][0]
            prev_frame.configure(fg_color=["gray86", "gray17"]) # Default

        self.selected_session_id = s_id
        
        # Highlight new selection
        if s_id in self.row_widgets:
            curr_frame = self.row_widgets[s_id][0]
            curr_frame.configure(fg_color=["gray75", "gray25"]) # Highlighted

    def load_mock_data(self):
        # Deprecated
        pass

    def on_start(self): print("Start clicked")
    def on_pause(self): print("Pause clicked")
    def on_stop(self): print("Stop clicked")
    
    def on_settings(self): 
        print("Settings clicked")
        from gui.components.settings_modal import SettingsModal
        SettingsModal(self)
        
    def on_add(self): 
        print("Add clicked")
        from gui.components.session_modal import SessionModal
        SessionModal(self)

    def on_edit(self): 
        print("Edit clicked")
        if not self.selected_session_id:
            print("Select session first")
            return
        from gui.components.session_modal import SessionModal
        SessionModal(self, session_id=self.selected_session_id)

    def on_delete(self): print("Delete clicked")
    
    def on_login(self): 
        if not self.selected_session_id:
            print("Please select a session first.")
            return

        session_data = self.sessions_data[self.selected_session_id]
        print(f"Launching Login Browser for session {session_data['name']}...")
        self.log_message(f"Launching Login Browser for session {session_data['name']}...")
        
        import threading
        import asyncio
        from utils.browser import BrowserManager
        
        def run_browser_task():
             # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
            manager = BrowserManager()
            loop.run_until_complete(manager.run_manual_login(session_data))
            loop.close()
            print("Browser closed.")
            self.after(0, lambda: self.log_message(f"Browser closed for {session_data['name']}"))

        # Run in separate thread to avoid freezing GUI
        thread = threading.Thread(target=run_browser_task, daemon=True)
        thread.start()

    def log_message(self, msg):
        if hasattr(self, 'log_window'):
            self.log_window.append_log(msg)

