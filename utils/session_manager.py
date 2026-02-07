import os
import hashlib
from pathlib import Path
from typing import Optional

class SessionManager:
    """
    Manages session files and sticky proxy mappings to ensure
    threads don't share cookies/sessions.
    """
    def __init__(self, base_dir="data/sessions"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_proxy_hash(self, proxy_data: Optional[dict]) -> str:
        """Helper to create a stable hash for a proxy configuration"""
        if not proxy_data:
            return "direct"
        
        # We use the server address as the unique identifier
        # assuming one proxy per server address usually
        server = proxy_data.get('server', 'direct')
        return hashlib.md5(server.encode()).hexdigest()

    def get_session_path(self, marketplace: str, proxy_data: Optional[dict]) -> str:
        """
        Returns a unique session file path for a given marketplace AND proxy.
        This ensures that if we switch proxies, we switch sessions (cookies).
        """
        proxy_hash = self._get_proxy_hash(proxy_data)
        filename = f"{marketplace}_session_{proxy_hash}.json"
        return str(self.base_dir / filename)

    def get_thread_proxy_path(self, marketplace: str, thread_id: int) -> str:
        """
        Returns the path to the 'sticky proxy' file for a specific thread.
        Each thread will try to keep using the same proxy until it fails.
        """
        filename = f"{marketplace}_thread_{thread_id}_proxy.json"
        return str(self.base_dir / filename)

    def clear_session(self, filepath: str):
        """Safely removes a session file"""
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                return True
        except OSError:
            pass
        return False
