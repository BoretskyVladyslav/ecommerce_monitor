import customtkinter as ctk
import threading
import asyncio
import os
import json
from tkinter import messagebox
from typing import Optional

# Adjust imports based on project structure
from utils.browser import BrowserManager
from parsers.shein import SheinParser
from utils.session_manager import SessionManager

class SessionModal(ctk.CTkToplevel):
    def __init__(self, master, **kwargs):
        super().__init__(master, **kwargs)
        
        self.title("Session Creator - Shein")
        self.geometry("500x600")
        self.resizable(False, False)
        
        # Managers
        self.browser_manager = BrowserManager()
        self.session_manager = SessionManager()
        
        # State
        self.browser_thread: Optional[threading.Thread] = None
        self.save_requested = False
        self.browser_running = False
        self.stop_event = threading.Event()
        
        # UI Setup
        self._create_widgets()
        
        # Make modal behavior
        self.transient(master)
        self.grab_set()
        self.focus_set()

    def _create_widgets(self):
        # 1. Inputs Section
        inputs_frame = ctk.CTkFrame(self)
        inputs_frame.pack(fill="x", padx=20, pady=20)
        
        # Email
        ctk.CTkLabel(inputs_frame, text="Email:").pack(anchor="w", padx=10, pady=(10, 2))
        self.entry_email = ctk.CTkEntry(inputs_frame, placeholder_text="user@example.com")
        self.entry_email.pack(fill="x", padx=10, pady=(0, 10))
        
        # Password
        ctk.CTkLabel(inputs_frame, text="Password:").pack(anchor="w", padx=10, pady=(0, 2))
        self.entry_password = ctk.CTkEntry(inputs_frame, show="*", placeholder_text="********")
        self.entry_password.pack(fill="x", padx=10, pady=(0, 10))
        
        # Proxy
        ctk.CTkLabel(inputs_frame, text="Proxy (Optional):").pack(anchor="w", padx=10, pady=(0, 2))
        self.entry_proxy = ctk.CTkEntry(inputs_frame, placeholder_text="ip:port:user:pass or http://...")
        self.entry_proxy.pack(fill="x", padx=10, pady=(0, 15))
        
        # 2. Controls Section
        controls_frame = ctk.CTkFrame(self, fg_color="transparent")
        controls_frame.pack(fill="x", padx=20, pady=0)
        
        self.btn_launch = ctk.CTkButton(controls_frame, text="🚀 Launch Browser", 
            command=self.on_launch, height=40, font=("Arial", 14, "bold"))
        self.btn_launch.pack(fill="x", pady=(0, 10))
        
        self.btn_save = ctk.CTkButton(controls_frame, text="💾 Save Session", 
            command=self.on_save, height=40, font=("Arial", 14, "bold"), 
            state="disabled", fg_color="gray", hover_color="gray")
        self.btn_save.pack(fill="x", pady=(0, 10))
        
        # 3. Logs Section
        logs_frame = ctk.CTkFrame(self)
        logs_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        
        ctk.CTkLabel(logs_frame, text="Automation Logs:", anchor="w").pack(fill="x", padx=5, pady=5)
        
        self.log_box = ctk.CTkTextbox(logs_frame, state="disabled", wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=5, pady=5)
        
    def log(self, message):
        """Thread-safe logging"""
        self.after(0, lambda: self._log_internal(message))
        
    def _log_internal(self, message):
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f">> {message}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def on_launch(self):
        email = self.entry_email.get().strip()
        password = self.entry_password.get().strip()
        proxy = self.entry_proxy.get().strip()
        
        if not email or not password:
            messagebox.showerror("Error", "Email and Password are required!")
            self.lift() # Bring back to top
            return
            
        # Disable inputs
        self.btn_launch.configure(state="disabled")
        self.entry_email.configure(state="disabled")
        self.entry_password.configure(state="disabled")
        self.entry_proxy.configure(state="disabled")
        
        self.log("Initializing browser launch sequence...")
        
        # Start browser thread
        self.browser_thread = threading.Thread(
            target=self._run_browser_task,
            args=(email, password, proxy),
            daemon=True
        )
        self.browser_thread.start()
        
    def _run_browser_task(self, email, password, proxy):
        try:
             asyncio.run(self._browser_logic(email, password, proxy))
        except Exception as e:
            self.log(f"Thread Error: {e}")
        
    async def _browser_logic(self, email, password, proxy_str):
        self.log("Starting Playwright engine...")
        
        session_data = {
            "type": "shein",
            "proxy": proxy_str if proxy_str else None,
            "headless": False,  # MUST be visible for manual interaction
            "email": email
        }
        
        from playwright.async_api import async_playwright
        
        async with async_playwright() as p:
            try:
                # 1. Launch Browser
                self.log(f"Launching stealth browser...")
                context, browser = await self.browser_manager.get_context(
                    p, session_data, 
                    block_resources=False, 
                    block_images=False,
                    simplified=False
                )
                
                self.browser_running = True
                
                # 2. Navigate
                page = await context.new_page()
                parser = SheinParser(page, session_data)
                
                self.log("Navigating to Shein login...")
                try:
                    await page.goto("https://www.shein.com/user/auth/login", timeout=60000)
                except Exception as e:
                    self.log(f"Navigation warning: {e}")
                
                # 3. Create Handover State
                self.log("Handling initial popups...")
                await parser.close_popups(aggressive=True)
                
                self.log("Attempting to auto-fill credentials...")
                try:
                    # Typo in user request said "human_type(selector, text)"
                    # We use the Parser's methods if possible, or fallback to simple type
                    
                    # Try Email
                    typed_email = await parser.human_type("input[type='email']", email)
                    if not typed_email:
                         self.log("⚠️ Could not auto-type email. Please type manually.")
                    else:
                        await asyncio.sleep(0.5)
                        
                    # Try Password
                    typed_pass = await parser.human_type("input[type='password']", password)
                    if not typed_pass:
                        self.log("⚠️ Could not auto-type password.")
                        
                except Exception as e:
                    self.log(f"Auto-fill warning: {e}. Please fill manually.")

                self.log("--------------------------------------------------")
                self.log("✅ BROWSER HANDOVER COMPLETE")
                self.log("--------------------------------------------------")
                self.log("👉 ACTION REQUIRED:")
                self.log("1. Solve any Captcha / Slider in the browser.")
                self.log("2. Click 'Sign In' button.")
                self.log("3. Verify you are fully logged in.")
                self.log("4. CLICK 'Save Session' below when done.")
                
                # Enable Save Button (Thread-safe)
                def enable_save():
                    self.btn_save.configure(state="normal", fg_color="#2ecc71", hover_color="#27ae60")
                self.after(0, enable_save)
                
                # 4. Wait Loop
                while not self.stop_event.is_set():
                    # Check if saved requested
                    if self.save_requested:
                        self.log("💾 Saving session data...")
                        
                        # Save Storage State (Cookies + LocalStorage)
                        storage = await context.storage_state()
                        
                        # Construct filename
                        safe_email = email.replace("@", "_").replace(".", "_")
                        filename = f"shein_session_{safe_email}.json"
                        filepath = os.path.join(self.session_manager.base_dir, filename)
                        
                        # Use SessionManager to save
                        if self.session_manager.save_storage_state(filepath, storage):
                            self.log(f"✅ Session saved successfully to:\n{filename}")
                            
                            # Also save standalone cookies for backup
                            cookies = await context.cookies()
                            cookie_path = filepath.replace(".json", "_cookies.json")
                            self.session_manager.save_cookies(cookie_path, cookies)
                        else:
                            self.log("❌ Error saving session file!")
                        
                        self.log("Closing browser in 3 seconds...")
                        await asyncio.sleep(3)
                        break
                    
                    # Check if browser was closed by user
                    try:
                        if not context.pages:
                            self.log("⚠️ Browser closed by user. Session NOT saved.")
                            break
                    except:
                        break
                        
                    await asyncio.sleep(0.5)
                
                await context.close()
                await browser.close()
                self.browser_running = False
                
                if self.save_requested:
                    self.log("Done. Window closing...")
                    self.after(1500, self.destroy)
                
            except Exception as e:
                self.log(f"CRITICAL ERROR: {e}")
                import traceback
                traceback.print_exc()
                self.browser_running = False

    def on_save(self):
        self.save_requested = True
        self.btn_save.configure(state="disabled", text="Saving...")
