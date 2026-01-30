import customtkinter as ctk
import asyncio
import threading
from fake_useragent import UserAgent
from database.db_manager import DatabaseManager

class SessionModal(ctk.CTkToplevel):
    def __init__(self, master, session_id=None):
        super().__init__(master)
        self.session_id = session_id
        self.title("Edit Session" if session_id else "Add Session")
        self.geometry("500x600")
        
        # Make modal
        self.transient(master)
        self.grab_set()
        
        self.grid_columnconfigure(1, weight=1)
        
        # Name
        ctk.CTkLabel(self, text="Session Name:").grid(row=0, column=0, padx=10, pady=10, sticky="w")
        self.entry_name = ctk.CTkEntry(self)
        self.entry_name.grid(row=0, column=1, padx=10, pady=10, sticky="ew")

        # Type (Dropdown)
        ctk.CTkLabel(self, text="Marketplace:").grid(row=1, column=0, padx=10, pady=10, sticky="w")
        self.combo_type = ctk.CTkComboBox(self, values=["amazon", "shein", "temu", "aliexpress"])
        self.combo_type.grid(row=1, column=1, padx=10, pady=10, sticky="ew")

        # Proxy
        ctk.CTkLabel(self, text="Proxy (http://user:pass@ip:port):").grid(row=2, column=0, padx=10, pady=10, sticky="w")
        self.entry_proxy = ctk.CTkEntry(self)
        self.entry_proxy.grid(row=2, column=1, padx=10, pady=10, sticky="ew")

        # User Agent
        ctk.CTkLabel(self, text="User Agent:").grid(row=3, column=0, padx=10, pady=10, sticky="w")
        self.textbox_ua = ctk.CTkTextbox(self, height=100)
        self.textbox_ua.grid(row=3, column=1, padx=10, pady=10, sticky="ew")
        
        # Generate UA Button
        self.btn_gen_ua = ctk.CTkButton(self, text="Generate Random UA", command=self.generate_ua, fg_color="gray")
        self.btn_gen_ua.grid(row=4, column=1, padx=10, pady=5, sticky="e")

        # Status (Only for edit)
        if self.session_id:
            ctk.CTkLabel(self, text="Status:").grid(row=5, column=0, padx=10, pady=10, sticky="w")
            self.combo_status = ctk.CTkComboBox(self, values=["Ready", "Wait", "Error", "Run"])
            self.combo_status.grid(row=5, column=1, padx=10, pady=10, sticky="ew")

        # Save Button
        self.btn_save = ctk.CTkButton(self, text="Save Session", command=self.on_save, fg_color="green")
        self.btn_save.grid(row=6, column=0, columnspan=2, padx=10, pady=20)

        # Load data if editing
        if self.session_id:
            self.load_session_data()
        else:
            self.generate_ua() # Pre-fill for new

    def generate_ua(self):
        try:
            # Using default UserAgent() as filters caused library errors
            ua = UserAgent()
            new_ua = ua.random
        except Exception as e:
            print(f"UA Library Error: {e}")
            # Minimal fallback just to prevent crash
            new_ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
        
        self.textbox_ua.delete("0.0", "end")
        self.textbox_ua.insert("0.0", new_ua)

    def load_session_data(self):
        # Fetch from DB in thread/async
        def fetch():
            async def _async_fetch():
                db = DatabaseManager()
                await db.init_db() # Ensure pool
                sessions = await db.fetch_all("SELECT * FROM sessions WHERE id=%s", (self.session_id,))
                await db.close()
                return sessions[0] if sessions else None

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            data = loop.run_until_complete(_async_fetch())
            loop.close()
            
            if data:
                self.after(0, lambda: self.populate_fields(data))

        threading.Thread(target=fetch, daemon=True).start()

    def populate_fields(self, data):
        self.entry_name.delete(0, "end")
        self.entry_name.insert(0, data['name'])
        self.combo_type.set(data['type'])
        if data['proxy']:
            self.entry_proxy.delete(0, "end")
            self.entry_proxy.insert(0, data['proxy'])
        if data['user_agent']:
            self.textbox_ua.delete("0.0", "end")
            self.textbox_ua.insert("0.0", data['user_agent'])
        if hasattr(self, 'combo_status'):
            self.combo_status.set(data['status'])

    def on_save(self):
        name = self.entry_name.get()
        s_type = self.combo_type.get()
        proxy = self.entry_proxy.get()
        user_agent = self.textbox_ua.get("0.0", "end").strip()
        status = self.combo_status.get() if hasattr(self, 'combo_status') else "Ready"
        
        if not name:
            print("Name required")
            return

        def save_task():
            async def _async_save():
                db = DatabaseManager()
                await db.init_db()
                
                if self.session_id:
                    query = """
                        UPDATE sessions 
                        SET name=%s, type=%s, proxy=%s, user_agent=%s, status=%s
                        WHERE id=%s
                    """
                    await db.execute(query, (name, s_type, proxy, user_agent, status, self.session_id))
                else:
                    query = """
                        INSERT INTO sessions (name, type, proxy, user_agent, status)
                        VALUES (%s, %s, %s, %s, %s)
                    """
                    await db.execute(query, (name, s_type, proxy, user_agent, status))
                
                await db.close()

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_async_save())
            loop.close()
            
            # Refresh parent
            self.after(0, self.master.reload_sessions_from_db)
            self.after(0, self.destroy)

        threading.Thread(target=save_task, daemon=True).start()
