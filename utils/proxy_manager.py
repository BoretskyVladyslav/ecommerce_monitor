import re
import random
import json
import sys
import requests
from pathlib import Path

class ProxyManager:
    def __init__(self, proxy_file="proxies.txt"):
        # 🔧 Визначаємо базову папку (де лежить .exe або main.py)
        if getattr(sys, 'frozen', False):
            # Якщо це .exe
            base_dir = Path(sys.executable).parent
        else:
            # Якщо це Python скрипт
            base_dir = Path(__file__).parent.parent  # utils/proxy_manager.py -> проект
        
        # Використовуємо абсолютний шлях
        self.proxy_file = base_dir / proxy_file
        print(f"📁 ProxyManager using: {self.proxy_file}")
        
        self.proxies = []
        self.current_index = 0
        self.load_proxies()
        
        # Auto-download from URL if local file is empty
        if not self.proxies:
            from config.settings import settings
            if settings.PROXY_URL:
                print(f"🔄 Auto-updating proxies from URL: {settings.PROXY_URL}...")
                self.update_from_url(settings.PROXY_URL)
        
        # Randomize starting position so different sessions don't use same proxy
        if self.proxies:
            self.current_index = random.randint(0, len(self.proxies) - 1)
            
        # 🚫 Blacklist for current session
        self.blacklisted_proxies = set()

    def get_next_proxy(self):
        if not self.proxies:
            return None
        
        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return proxy
    
    def load_proxies(self):
        self.proxies = [] # Reset
        if not self.proxy_file.exists():
            print(f"ℹ️ No proxies found in {self.proxy_file}. System will run in DIRECT mode.")
            return
        
        try:
            with open(self.proxy_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            print(f"📖 Read {len(lines)} lines from {self.proxy_file}")
        except Exception as e:
            print(f"⚠️ Error reading proxy file: {e}. System will run in DIRECT mode.")
            return
        
        # Load geo cache
        geo_cache = self._load_geo_cache()
        
        # Import settings for country filtering
        from config.settings import settings
        allowed_countries = [] # getattr(settings, 'PROXY_ALLOWED_COUNTRIES', []) -> DISABLED by user request
        
        # --- Pre-parse to get IPs ---
        parsed_configs = []
        ips_to_check = set()
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            config = self._parse_proxy_line(line)
            if config:
                parsed_configs.append(config)
                if allowed_countries:
                    ip = self._extract_ip(config['server'])
                    if ip and ip not in geo_cache:
                        ips_to_check.add(ip)

        # --- Batch Resolve Unknown IPs ---
        if allowed_countries and ips_to_check:
            print(f"🌍 Resolving {len(ips_to_check)} unknown proxy locations...")
            unknown_ips_list = list(ips_to_check)
            
            # Batch size 100 (API limit)
            batch_size = 100
            for i in range(0, len(unknown_ips_list), batch_size):
                batch = unknown_ips_list[i:i + batch_size]
                try:
                    # Using POST batch endpoint
                    response = requests.post(
                        "http://ip-api.com/batch?fields=query,countryCode", 
                        json=batch, 
                        timeout=10
                    )
                    if response.status_code == 200:
                        results = response.json()
                        for res in results:
                            # res is dict like {'query': '1.2.3.4', 'countryCode': 'US'}
                            q_ip = res.get('query')
                            c_code = res.get('countryCode')
                            if q_ip:
                                geo_cache[q_ip] = c_code
                    else:
                        print(f"⚠️ Geo-API batch error: {response.status_code}")
                except Exception as e:
                    print(f"⚠️ Geo-API request failed: {e}")
                
        # Save updated geo cache (so we don't query again)
        self._save_geo_cache(geo_cache)
        
        # --- Filter ---
        total_proxies = len(parsed_configs)
        filtered_proxies = 0
        
        for config in parsed_configs:
            if allowed_countries:
                ip = self._extract_ip(config['server'])
                # Look up in cache (now populated)
                country = geo_cache.get(ip)
                
                if country and country in allowed_countries:
                    self.proxies.append(config)
                    filtered_proxies += 1
                else:
                    # Debug print for rejected (optional, can be noisy)
                    # print(f"Skipping non-US proxy: {ip} ({country})")
                    pass
            else:
                self.proxies.append(config)
        
        print(f"📊 Parsed: {total_proxies} proxies, Filtered (Valid US): {filtered_proxies}, Final: {len(self.proxies)}")
        
        if self.proxies:
            if allowed_countries:
                print(f"✅ Loaded {len(self.proxies)} proxies from {total_proxies} (verified {', '.join(allowed_countries)})")
            else:
                print(f"✅ Loaded {len(self.proxies)} valid proxies from {self.proxy_file}")
        else:
            if allowed_countries:
                print(f"❌ 0 proxies matched the country filter {allowed_countries}!")
            else:
                print(f"ℹ️ No proxies found in {self.proxy_file}. System will run in DIRECT mode.")

    def _get_country(self, ip, cache):
        # Legacy method kept for compatibility if needed, but not used in new load_proxies
        return cache.get(ip)

    def _load_geo_cache(self):
        """Load geo cache from file"""
        cache_file = Path("proxy_geo_cache.json")
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {}

    def _save_geo_cache(self, cache):
        """Save geo cache to file"""
        cache_file = Path("proxy_geo_cache.json")
        try:
            with open(cache_file, 'w') as f:
                json.dump(cache, f, indent=2)
        except:
            pass
    
    def update_from_url(self, url):
        """Downloads proxies from URL and saves to file."""
        try:
            print(f"Downloading proxies from {url}...")
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                content = response.text
                if ":" in content:
                    with open(self.proxy_file, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print("Proxies updated from URL.")
                    self.load_proxies()
                    return True
                else:
                    print("Invalid content from URL")
            else:
                print(f"Failed to download proxies: {response.status_code}")
        except Exception as e:
            print(f"Error updating proxies: {e}")
        return False

    def save_manual_list(self, text):
        try:
            with open(self.proxy_file, 'w', encoding='utf-8') as f:
                f.write(text)
            self.load_proxies()
            return True
        except Exception as e:
            print(f"Error saving proxies: {e}")
            return False

    def _parse_proxy_line(self, line):
        parts = line.split(':')
        if len(parts) == 4:
            return {
                "server": f"http://{parts[0]}:{parts[1]}",
                "username": parts[2],
                "password": parts[3],
                "raw": line
            }
        elif len(parts) == 2:
             return {
                "server": f"http://{parts[0]}:{parts[1]}",
                "username": None,
                "password": None,
                "raw": line
            }
        return None
    
    def blacklist_proxy(self, proxy):
        """Marks a proxy as bad for this session."""
        if not proxy: return
        key = proxy.get('server')
        if key:
            self.blacklisted_proxies.add(key)
            print(f"🚫 Proxy Blacklisted: {key} (Total Blacklisted: {len(self.blacklisted_proxies)})")

    def get_random_proxy(self):
        if not self.proxies:
            return None
        # Filter out blacklisted
        available = [p for p in self.proxies if p.get('server') not in self.blacklisted_proxies]
        if not available:
            print("⚠️ All proxies blacklisted! Clearing blacklist to retry...")
            self.blacklisted_proxies.clear()
            available = self.proxies
        return random.choice(available)
    
    def get_all_proxies(self):
        return self.proxies.copy()
    
    def _extract_ip(self, server_url):
        try:
            # Remove protocol
            ip_port = server_url.split('://')[-1]
            # Remove port
            ip = ip_port.split(':')[0]
            return ip
        except:
            return None

    @property
    def proxy_count(self):
        return len(self.proxies)
