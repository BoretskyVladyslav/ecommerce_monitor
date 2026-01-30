import re
import random
from pathlib import Path

class ProxyManager:
    def __init__(self, proxy_file="proxies.txt"):
        self.proxy_file = Path(proxy_file)
        self.proxies = []
        self.current_index = 0
        self.load_proxies()

    def get_next_proxy(self):
        if not self.proxies:
            return None
        
        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return proxy
    
    def load_proxies(self):
        if not self.proxy_file.exists():
            print(f"ℹ️ No proxies found in {self.proxy_file}. System will run in DIRECT mode.")
            return
        
        try:
            with open(self.proxy_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except Exception as e:
            print(f"⚠️ Error reading proxy file: {e}. System will run in DIRECT mode.")
            return
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            proxy_config = self._parse_proxy_line(line)
            if proxy_config:
                self.proxies.append(proxy_config)
        
        if self.proxies:
            print(f"✅ Loaded {len(self.proxies)} valid proxies from {self.proxy_file}")
        else:
            print(f"ℹ️ No proxies found in {self.proxy_file}. System will run in DIRECT mode.")
    
    def _parse_proxy_line(self, line):
        pattern = r'^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+):([^:]+):(.+)$'
        match = re.match(pattern, line)
        
        if not match:
            print(f"⚠️ Invalid proxy format (skipped): {line}")
            return None
        
        ip, port, username, password = match.groups()
        
        if not self._validate_ip(ip):
            print(f"⚠️ Invalid IP address (skipped): {ip}")
            return None
        
        if not port.isdigit() or not (1 <= int(port) <= 65535):
            print(f"⚠️ Invalid port (skipped): {port}")
            return None
        
        return {
            "server": f"http://{ip}:{port}",
            "username": username,
            "password": password
        }
    
    def _validate_ip(self, ip):
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        
        try:
            return all(0 <= int(part) <= 255 for part in parts)
        except ValueError:
            return False
    
    def get_random_proxy(self):
        if not self.proxies:
            return None
        return random.choice(self.proxies)
    
    def get_all_proxies(self):
        return self.proxies.copy()
    
    @property
    def proxy_count(self):
        return len(self.proxies)
