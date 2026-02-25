import os
import json
import hashlib
import threading
import time
from pathlib import Path
from typing import Optional, Dict
from datetime import datetime, timedelta

class SessionManager:
    
    def __init__(self, base_dir="data/sessions"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file_locks = {}
        
    def _get_file_lock(self, filepath: str):
        with self._lock:
            if filepath not in self._file_locks:
                self._file_locks[filepath] = threading.Lock()
            return self._file_locks[filepath]
        
    def _get_proxy_hash(self, proxy_data: Optional[dict]) -> str:
        if not proxy_data:
            return "direct"
        
        server = proxy_data.get('server', 'direct')
        username = proxy_data.get('username', '')
        combined = f"{server}:{username}"
        return hashlib.md5(combined.encode()).hexdigest()[:12]
        
    def get_session_path(self, marketplace: str, proxy_data: Optional[dict]) -> str:
        proxy_hash = self._get_proxy_hash(proxy_data)
        filename = f"{marketplace}_session_{proxy_hash}.json"
        return str(self.base_dir / filename)
        
    def get_thread_proxy_path(self, marketplace: str, thread_id: int) -> str:
        filename = f"{marketplace}_thread_{thread_id}_proxy.json"
        return str(self.base_dir / filename)
        
    def save_storage_state(self, filepath: str, storage_state: Dict) -> bool:
        file_lock = self._get_file_lock(filepath)
        
        with file_lock:
            try:
                temp_path = f"{filepath}.tmp.{os.getpid()}.{threading.get_ident()}"
                
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(storage_state, f, indent=2, ensure_ascii=False)
                
                if os.path.exists(filepath):
                    backup_path = f"{filepath}.backup"
                    try:
                        if os.path.exists(backup_path):
                            os.remove(backup_path)
                        os.rename(filepath, backup_path)
                    except:
                        pass
                
                os.rename(temp_path, filepath)
                return True
            
            except Exception as e:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except:
                    pass
                return False
        
    def load_storage_state(self, filepath: str, validate: bool = True) -> Optional[Dict]:
        file_lock = self._get_file_lock(filepath)
        
        with file_lock:
            try:
                if not os.path.exists(filepath):
                    return None
                
                with open(filepath, 'r', encoding='utf-8') as f:
                    storage_state = json.load(f)
                
                if validate and not self._validate_storage_state(storage_state):
                    return None
                
                return storage_state
            
            except Exception as e:
                return None
        
    def _validate_storage_state(self, storage_state: Dict) -> bool:
        try:
            if not isinstance(storage_state, dict):
                return False
            
            cookies = storage_state.get('cookies', [])
            if not isinstance(cookies, list):
                return False
            
            if len(cookies) == 0:
                return False
            
            now = datetime.now()
            valid_cookies = 0
            
            for cookie in cookies:
                if not isinstance(cookie, dict):
                    continue
                
                expires = cookie.get('expires', -1)
                
                if expires == -1:
                    valid_cookies += 1
                    continue
                
                try:
                    expiry_date = datetime.fromtimestamp(expires)
                    if expiry_date > now:
                        valid_cookies += 1
                except:
                    continue
            
            if valid_cookies == 0:
                return False
            
            return True
            
        except Exception as e:
            return False
        
    def clear_session(self, filepath: str) -> bool:
        file_lock = self._get_file_lock(filepath)
        
        with file_lock:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                
                backup_path = f"{filepath}.backup"
                if os.path.exists(backup_path):
                    os.remove(backup_path)
                
                return True
            
            except Exception as e:
                return False
        
    def restore_from_backup(self, filepath: str) -> bool:
        file_lock = self._get_file_lock(filepath)
        
        with file_lock:
            try:
                backup_path = f"{filepath}.backup"
                
                if not os.path.exists(backup_path):
                    return False
                
                if os.path.exists(filepath):
                    os.remove(filepath)
                
                with open(backup_path, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
                
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(backup_data, f, indent=2, ensure_ascii=False)
                
                return True
            
            except Exception as e:
                return False
        
    def get_session_age(self, filepath: str) -> Optional[int]:
        try:
            if not os.path.exists(filepath):
                return None
            
            mtime = os.path.getmtime(filepath)
            age_seconds = int(time.time() - mtime)
            return age_seconds
            
        except Exception as e:
            return None
        
    def is_session_fresh(self, filepath: str, max_age_hours: int = 24) -> bool:
        try:
            age_seconds = self.get_session_age(filepath)
            
            if age_seconds is None:
                return False
            
            max_age_seconds = max_age_hours * 3600
            return age_seconds < max_age_seconds
            
        except Exception as e:
            return False
        
    def save_cookies(self, filepath: str, cookies: list) -> bool:
        storage_state = {
            "cookies": cookies,
            "origins": []
        }
        return self.save_storage_state(filepath, storage_state)
        
    def load_cookies(self, filepath: str, validate: bool = True) -> Optional[list]:
        storage_state = self.load_storage_state(filepath, validate=validate)
        
        if storage_state and "cookies" in storage_state:
            return storage_state["cookies"]
        
        return None