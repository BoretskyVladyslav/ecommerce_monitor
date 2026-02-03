import customtkinter as ctk
import asyncio
import threading
from gui.components.settings_modal import SettingsModal
from utils.monitor_engine import MonitorEngine

class MainWindow(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        # --- Layout Configuration ---
        self.grid_rowconfigure(1, weight=1) # Tabview takes remaining space
        self.grid_columnconfigure(0, weight=1)

        # ==========================================================
        # 1. TOP PANEL: START | STOP | SETTINGS
        # ==========================================================
        self.top_panel = ctk.CTkFrame(self, height=60, corner_radius=0)
        self.top_panel.grid(row=0, column=0, sticky="ew", padx=0, pady=0)
        
        # Start Button (Green)
        self.btn_start = ctk.CTkButton(self.top_panel, text="START", fg_color="#2ecc71", hover_color="#27ae60", 
                                       width=120, command=self.on_start)
        self.btn_start.pack(side="left", padx=20, pady=15)
        
        # Stop Button (Red)
        self.btn_stop = ctk.CTkButton(self.top_panel, text="STOP", fg_color="#e74c3c", hover_color="#c0392b", 
                                      width=100, command=self.on_stop)
        self.btn_stop.pack(side="left", padx=10, pady=15)
        
        # Settings Button (Icon/Text)
        self.btn_settings = ctk.CTkButton(self.top_panel, text="⚙️ Settings", fg_color="transparent", border_width=1, 
                                           text_color=("gray10", "gray90"), command=self.on_settings)
        self.btn_settings.pack(side="right", padx=20, pady=15)

        # ==========================================================
        # 2. TABVIEW: MONITOR | PROXY MANAGER
        # ==========================================================
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=1, column=0, sticky="nsew", padx=10, pady=10)
        
        self.tab_monitor = self.tabview.add("Monitor")
        self.tab_proxy = self.tabview.add("Proxy Manager")
        
        # Configure layout for tabs
        self.tab_monitor.grid_columnconfigure(0, weight=1)
        self.tab_monitor.grid_rowconfigure(0, weight=1) # Table expands
        
        self.tab_proxy.grid_columnconfigure(0, weight=1)

        # ==========================================================
        # TAB 1: MONITOR (Table + Log)
        # ==========================================================
        
        # --- A. Active Processes Table ---
        self.monitor_frame = ctk.CTkFrame(self.tab_monitor)
        self.monitor_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        self.monitor_frame.grid_columnconfigure(0, weight=1)
        self.monitor_frame.grid_rowconfigure(1, weight=1)
        
        # Table Headers
        self.table_headers = ctk.CTkFrame(self.monitor_frame, height=30)
        self.table_headers.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        
        headers = ["Thread ID", "Product ID", "Proxy IP", "Status"]
        # Grid weights for columns
        self.table_headers.grid_columnconfigure(0, weight=1) # Thread ID
        self.table_headers.grid_columnconfigure(1, weight=2) # Product ID
        self.table_headers.grid_columnconfigure(2, weight=2) # Proxy IP
        self.table_headers.grid_columnconfigure(3, weight=2) # Status
        
        for i, h in enumerate(headers):
            lbl = ctk.CTkLabel(self.table_headers, text=h, font=("Arial", 12, "bold"))
            lbl.grid(row=0, column=i, sticky="ew")

        # Scrollable rows area (Now with dictionary for updates)
        self.table_scroll = ctk.CTkScrollableFrame(self.monitor_frame)
        self.table_scroll.grid(row=1, column=0, sticky="nsew", padx=5, pady=0)
        self.table_scroll.grid_columnconfigure(0, weight=1) # Thread ID
        self.table_scroll.grid_columnconfigure(1, weight=2) # Product ID
        self.table_scroll.grid_columnconfigure(2, weight=2) # Proxy IP
        self.table_scroll.grid_columnconfigure(3, weight=2) # Status
        
        self.rows = {} # option_id -> row_widgets (list)

        # --- B. System Log ---
        self.log_label = ctk.CTkLabel(self.tab_monitor, text="System Log", anchor="w")
        self.log_label.grid(row=2, column=0, sticky="w", padx=5, pady=(10,0))
        
        self.log_textbox = ctk.CTkTextbox(self.tab_monitor, height=150, state="disabled")
        self.log_textbox.grid(row=3, column=0, sticky="ew", padx=5, pady=5)

        # ==========================================================
        # TAB 2: PROXY MANAGER
        # ==========================================================
        
        # 1. Webshare URL
        self.proxy_url_label = ctk.CTkLabel(self.tab_proxy, text="Proxy Webshare URL (Auto-update):", anchor="w")
        self.proxy_url_label.pack(fill="x", padx=10, pady=(20, 5))
        
        self.proxy_url_entry = ctk.CTkEntry(self.tab_proxy, placeholder_text="https://proxy.webshare.io/api/...")
        self.proxy_url_entry.pack(fill="x", padx=10, pady=(0, 15))
        
        # 2. Manual List
        self.manual_proxy_label = ctk.CTkLabel(self.tab_proxy, text="Manual List (ip:port:user:pass):", anchor="w")
        self.manual_proxy_label.pack(fill="x", padx=10, pady=(5, 5))
        
        self.manual_proxy_text = ctk.CTkTextbox(self.tab_proxy, height=200)
        self.manual_proxy_text.pack(fill="x", padx=10, pady=(0, 15))
        
        # 3. Actions & Stats
        self.proxy_actions_frame = ctk.CTkFrame(self.tab_proxy, fg_color="transparent")
        self.proxy_actions_frame.pack(fill="x", padx=10, pady=5)
        
        self.btn_save_proxies = ctk.CTkButton(self.proxy_actions_frame, text="Update / Save Proxies", command=self.on_save_proxies)
        self.btn_save_proxies.pack(side="left")
        
        self.proxy_count_label = ctk.CTkLabel(self.proxy_actions_frame, text="Loaded Proxies: 0", font=("Arial", 14, "bold"))
        self.proxy_count_label.pack(side="right")
        
        # --- LOGIC INITIALIZATION ---
        self.engine = MonitorEngine(update_callback=self.update_row_safe, log_callback=self.log_safe)
        self.update_proxy_count() # Init count

    def update_row_safe(self, t_id, p_id, ip, status):
        """Thread-safe GUI update for table rows."""
        self.after(0, lambda: self._update_row(t_id, p_id, ip, status))

    def _update_row(self, t_id, p_id, ip, status):
        """Internal method to update or create a row."""
        # Use p_id (Product ID / Option ID) as key
        key = str(p_id) 
        
        color = "gray"
        if "Checking" in status: color = "orange"
        if "OK" in status: color = "green"
        if "Sold Out" in status: color = "red"
        if "Error" in status: color = "red"

        if key in self.rows:
            # Update existing status label (index 3)
            # Row Widgets: [t_id_lbl, p_id_lbl, ip_lbl, status_lbl]
            widgets = self.rows[key]
            widgets[2].configure(text=ip) # Update IP just in case
            widgets[3].configure(text=status, text_color=color)
        else:
            # Create new
            row = ctk.CTkFrame(self.table_scroll, fg_color="transparent")
            row.pack(fill="x", pady=2)
            row.grid_columnconfigure(0, weight=1)
            row.grid_columnconfigure(1, weight=2)
            row.grid_columnconfigure(2, weight=2)
            row.grid_columnconfigure(3, weight=2)
            
            w1 = ctk.CTkLabel(row, text=t_id)
            w1.grid(row=0, column=0)
            w2 = ctk.CTkLabel(row, text=p_id)
            w2.grid(row=0, column=1)
            w3 = ctk.CTkLabel(row, text=ip)
            w3.grid(row=0, column=2)
            w4 = ctk.CTkLabel(row, text=status, text_color=color)
            w4.grid(row=0, column=3)
            
            self.rows[key] = [w1, w2, w3, w4]

    def log_safe(self, msg):
        self.after(0, lambda: self.log(msg))

    def log(self, msg):
        self.log_textbox.configure(state="normal")
        self.log_textbox.insert("end", f">> {msg}\n")
        self.log_textbox.see("end")
        self.log_textbox.configure(state="disabled")

    def update_proxy_count(self):
        count = self.engine.proxy_manager.proxy_count
        self.proxy_count_label.configure(text=f"Loaded Proxies: {count}")

    # --- Callbacks ---
    def on_start(self):
        self.log("Starting Engine in background thread...")
        
        # Re-set concurrency limit in case settings changed
        self.engine.update_settings() 
        
        self.thread = threading.Thread(target=self._async_thread_target, daemon=True)
        self.thread.start()

    def _async_thread_target(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self.engine.start())
        try:
            loop.run_forever()
        except:
            pass

    def on_stop(self):
        self.log("Stopping Engine...")
        self.engine.running = False
        self.log("Signal sent. Engine will stop after current cycle.")

    def on_settings(self):
        SettingsModal(self)
        
    def on_save_proxies(self):
        url = self.proxy_url_entry.get()
        manual = self.manual_proxy_text.get("1.0", "end").strip()
        
        if url:
             self.log(f"Downloading proxies from {url}...")
             if self.engine.proxy_manager.update_from_url(url):
                 self.log("Proxies updated from URL.")
        
        if manual:
            self.log("Saving manual proxies...")
            if self.engine.proxy_manager.save_manual_list(manual):
                self.log("Manual list saved.")
                
        self.update_proxy_count()


