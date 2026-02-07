import customtkinter as ctk
from config.settings import settings
import json
import os

class SettingsModal(ctk.CTkToplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Configuration")
        self.geometry("500x550")
        self.resizable(False, False)
        
        # Center the window
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"+{x}+{y}")
        
        self.grab_set() 
        
        self.fields = {} # Store entry widgets

        # Scrollable Frame for settings
        self.scroll = ctk.CTkScrollableFrame(self)
        self.scroll.pack(fill="both", expand=True, padx=10, pady=10)
        
        # ==========================
        # 1. DATABASE SETTINGS
        # ==========================
        ctk.CTkLabel(self.scroll, text="Database Settings", font=("Arial", 14, "bold"), text_color="#3498db").pack(anchor="w", pady=(10, 5))
        
        self.add_field("DB Host:", "db_host", settings.DB_HOST)
        self.add_field("DB Port:", "db_port", str(settings.DB_PORT))
        self.add_field("DB User:", "db_user", settings.DB_USER)
        self.add_field("DB Password:", "db_pass", settings.DB_PASSWORD, is_password=True)
        self.add_field("DB Name:", "db_name", settings.DB_NAME)

        # ==========================
        # 2. APPLICATION SETTINGS
        # ==========================
        ctk.CTkLabel(self.scroll, text="Application Settings", font=("Arial", 14, "bold"), text_color="#3498db").pack(anchor="w", pady=(20, 5))
        
        self.add_field("Threads (Concurrent Checks):", "threads", str(settings.THREADS))
        
        # Headless Checkbox
        self.var_headless = ctk.BooleanVar(value=settings.HEADLESS)
        container = ctk.CTkFrame(self.scroll, fg_color="transparent")
        container.pack(fill="x", pady=5)
        ctk.CTkLabel(container, text="Headless Mode (Hidden Browser):", width=200, anchor="w").pack(side="left")
        ctk.CTkCheckBox(container, text="", variable=self.var_headless).pack(side="left")
        
        # ==========================
        # 3. PLATFORM CONTROL
        # ==========================
        ctk.CTkLabel(self.scroll, text="Platform Control (Kill Switches)", font=("Arial", 14, "bold"), text_color="#3498db").pack(anchor="w", pady=(20, 5))
        
        # Temu Checkbox
        self.var_enable_temu = ctk.BooleanVar(value=settings.ENABLE_TEMU)
        container_temu = ctk.CTkFrame(self.scroll, fg_color="transparent")
        container_temu.pack(fill="x", pady=5)
        ctk.CTkLabel(container_temu, text="Enable Temu:", width=200, anchor="w").pack(side="left")
        ctk.CTkCheckBox(container_temu, text="", variable=self.var_enable_temu).pack(side="left")
        
        # Shein Checkbox
        self.var_enable_shein = ctk.BooleanVar(value=settings.ENABLE_SHEIN)
        container_shein = ctk.CTkFrame(self.scroll, fg_color="transparent")
        container_shein.pack(fill="x", pady=5)
        ctk.CTkLabel(container_shein, text="Enable Shein:", width=200, anchor="w").pack(side="left")
        ctk.CTkCheckBox(container_shein, text="", variable=self.var_enable_shein).pack(side="left")
        
        # AliExpress Checkbox
        self.var_enable_aliexpress = ctk.BooleanVar(value=settings.ENABLE_ALIEXPRESS)
        container_aliexpress = ctk.CTkFrame(self.scroll, fg_color="transparent")
        container_aliexpress.pack(fill="x", pady=5)
        ctk.CTkLabel(container_aliexpress, text="Enable AliExpress:", width=200, anchor="w").pack(side="left")
        ctk.CTkCheckBox(container_aliexpress, text="", variable=self.var_enable_aliexpress).pack(side="left")
        
        self.add_field("Min Delay (sec):", "delay_min", str(settings.DELAY_MIN))
        self.add_field("Max Delay (sec):", "delay_max", str(settings.DELAY_MAX))

        # ==========================
        # 4. CAPTCHA SETTINGS
        # ==========================
        ctk.CTkLabel(self.scroll, text="Captcha Settings (2Captcha)", font=("Arial", 14, "bold"), text_color="#3498db").pack(anchor="w", pady=(20, 5))
        
        # Load current key from file
        self.captcha_config_path = os.path.join(os.getcwd(), 'config', 'captcha_config.json')
        current_api_key = ""
        try:
            if os.path.exists(self.captcha_config_path):
                with open(self.captcha_config_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    current_api_key = data.get('2captcha', {}).get('api_key', '')
        except Exception as e:
            print(f"Error loading captcha config: {e}")

        self.add_field("API Key:", "captcha_key", current_api_key, is_password=False)


        # Save Button
        self.btn_save = ctk.CTkButton(self, text="Save Configuration", command=self.on_save, height=40, font=("Arial", 14, "bold"))
        self.btn_save.pack(fill="x", padx=20, pady=20)
        
    def add_field(self, label_text, key, default_val, is_password=False):
        container = ctk.CTkFrame(self.scroll, fg_color="transparent")
        container.pack(fill="x", pady=2)
        
        ctk.CTkLabel(container, text=label_text, width=150, anchor="w").pack(side="left")
        
        entry = ctk.CTkEntry(container, show="*" if is_password else "")
        entry.insert(0, str(default_val))
        entry.pack(side="left", fill="x", expand=True)
        
        # --- FIX: FORCE PASTE FOR NON-ENGLISH LAYOUTS ---
        def force_paste(event):
            try:
                # Get text from clipboard
                clipboard = self.clipboard_get()
                # Insert at current cursor position
                entry.insert("insert", clipboard)
                return "break" # Prevent default behavior
            except:
                pass

        # Bind Ctrl+V (and Control-v for completeness)
        entry.bind("<Control-v>", force_paste)
        entry.bind("<Control-V>", force_paste)
        # ------------------------------------------------
        
        if not hasattr(self, 'fields'): self.fields = {}
        self.fields[key] = entry

    def on_save(self):
        # Update Settings Object
        try:
            settings.DB_HOST = self.fields['db_host'].get()
            settings.DB_PORT = int(self.fields['db_port'].get())
            settings.DB_USER = self.fields['db_user'].get()
            settings.DB_PASSWORD = self.fields['db_pass'].get()
            settings.DB_NAME = self.fields['db_name'].get()
            
            settings.THREADS = int(self.fields['threads'].get())
            settings.HEADLESS = self.var_headless.get()
            settings.DELAY_MIN = int(self.fields['delay_min'].get())
            settings.DELAY_MAX = int(self.fields['delay_max'].get())
            
            # Platform Control
            settings.ENABLE_TEMU = self.var_enable_temu.get()
            settings.ENABLE_SHEIN = self.var_enable_shein.get()
            settings.ENABLE_ALIEXPRESS = self.var_enable_aliexpress.get()
            
            # --- Save Captcha Config ---
            new_captcha_key = self.fields['captcha_key'].get()
            try:
                data = {}
                # Try load existing to preserve other settings
                if os.path.exists(self.captcha_config_path):
                    try:
                        with open(self.captcha_config_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                    except: pass # Start fresh if corrupt
                
                # Set Defaults if creating new or missing fields
                if "service" not in data: data["service"] = "2captcha"
                if "enabled" not in data: data["enabled"] = True
                if "max_retries" not in data: data["max_retries"] = 3
                
                # Ensure 2captcha section exists
                if "2captcha" not in data: 
                    data["2captcha"] = {
                        "api_url": "https://2captcha.com",
                        "timeout_seconds": 120,
                        "poll_interval_seconds": 5
                    }
                
                # Update Key
                data['2captcha']['api_key'] = new_captcha_key
                
                # Ensure Pricing defaults (optional but good for UI consistency)
                if "pricing" not in data:
                    data["pricing"] = {
                        "2captcha_slider": 2.99,
                        "2captcha_recaptcha": 2.99,
                        "2captcha_geetest": 2.99
                    }

                # Ensure directory exists
                os.makedirs(os.path.dirname(self.captcha_config_path), exist_ok=True)

                with open(self.captcha_config_path, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2)
                print(f"✅ Updated/Created Captcha Config with Key")

            except Exception as e:
                 print(f"❌ Error saving captcha config: {e}")
            
            # Update MAX_CONCURRENT_BROWSERS to match THREADS for logic consistency
            settings.MAX_CONCURRENT_BROWSERS = settings.THREADS
            
            # --- Persist to Database (Async in background) ---
            import threading
            import asyncio
            from utils.config_manager import ConfigManager
            
            def save_to_db_task():
                try:
                    asyncio.run(ConfigManager.save_all_settings())
                except Exception as ex:
                    print(f"DB Save Error: {ex}")
            
            threading.Thread(target=save_to_db_task, daemon=True).start()
            
            print("✅ Configuration Saved Successfully")
            self.destroy()
        except ValueError as e:
            print(f"❌ Error saving settings: {e}")
