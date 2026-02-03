import re
import random
import json
import requests
from pathlib import Path

class ProxyManager:
    def __init__(self, proxy_file="proxies.txt"):
        self.proxy_file = Path(proxy_file)
        self.proxies = []
        self.current_index = 0
        self.load_proxies()
        # Randomize starting position so different sessions don't use same proxy
        if self.proxies:
            self.current_index = random.randint(0, len(self.proxies) - 1)

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
        except Exception as e:
            print(f"⚠️ Error reading proxy file: {e}. System will run in DIRECT mode.")
            return
        
        # Load geo cache
        geo_cache = self._load_geo_cache()
        
        # Import settings for country filtering
        from config.settings import settings
        allowed_countries = getattr(settings, 'PROXY_ALLOWED_COUNTRIES', [])
        
        total_proxies = 0
        filtered_proxies = 0
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            proxy_config = self._parse_proxy_line(line)
            if proxy_config:
                total_proxies += 1
                
                # Check country filter if enabled
                if allowed_countries:
                    ip = self._extract_ip(proxy_config['server'])
                    country = self._get_country(ip, geo_cache)
                    
                    if country and country in allowed_countries:
                        self.proxies.append(proxy_config)
                        filtered_proxies += 1
                    else:
                        # Skip this proxy
                        pass
                else:
                    # No filter, add all
                    self.proxies.append(proxy_config)
        
        # Save updated geo cache
        self._save_geo_cache(geo_cache)
        
        if self.proxies:
            if allowed_countries:
                print(f"✅ Loaded {len(self.proxies)} proxies from {total_proxies} (filtered for {', '.join(allowed_countries)})")
            else:
                print(f"✅ Loaded {len(self.proxies)} valid proxies from {self.proxy_file}")
        else:
            print(f"ℹ️ No proxies found in {self.proxy_file}. System will run in DIRECT mode.")
    
    def update_from_url(self, url):
        """Downloads proxies from URL and saves to file."""
        try:
            print(f"Downloading proxies from {url}...")
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                content = response.text
                # Simple validation: check if it looks like proxy list
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
        # Supports ip:port:user:pass or user:pass@ip:port
        # Simple parser for ip:port:user:pass
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
    
    def get_random_proxy(self):
        if not self.proxies:
            return None
        return random.choice(self.proxies)
    
    def get_all_proxies(self):
        return self.proxies.copy()
    
    def _extract_ip(self, server_url):
        """Extract IP from server URL like 'http://1.2.3.4:8080'"""
        try:
            # Remove protocol
            ip_port = server_url.split('://')[-1]
            # Remove port
            ip = ip_port.split(':')[0]
            return ip
        except:
            return None
    
    def _get_country(self, ip, cache):
        """Get country code for IP using cache or API"""
        if not ip:
            return None
            
        # Check cache first
        if ip in cache:
            return cache[ip]
        
        # Query API
        try:
            response = requests.get(f"http://ip-api.com/json/{ip}?fields=countryCode", timeout=3)
            if response.status_code == 200:
                data = response.json()
                country = data.get('countryCode', None)
                cache[ip] = country
                return country
        except Exception as e:
            # Silently fail on API errors
            pass
        
        return None
    
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
    
    @property
    def proxy_count(self):
        return len(self.proxies)
