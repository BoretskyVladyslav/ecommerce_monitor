"""
Configuration settings for ecommerce_monitor.
Hardcoded for production deployment.
"""

class Settings:
    """Application settings - hardcoded for client delivery."""

    DB_HOST: str = "46.102.156.248"
    DB_PORT: int = 3306
    DB_USER: str = "etsycrm"
    DB_PASSWORD: str = "BiGHcS7cTnLh2Gew"
    DB_NAME: str = "etsycrm"

    MAX_CONCURRENT_BROWSERS: int = 2
    BROWSER_TIMEOUT: int = 30000  
    HEADLESS: bool = False  

    PROXY_URL: str = None
    
    # Proxy Country Filtering (empty list = all countries allowed)
    # Example: ["US", "GB", "DE", "FR"] for USA, UK, Germany, France
    PROXY_ALLOWED_COUNTRIES: list = ["US"]  # Only USA proxies
    
    # User Preferences
    THREADS: int = 5
    DELAY_MIN: int = 2
    DELAY_MAX: int = 5
    
    # Platform Control (Kill Switches)
    ENABLE_TEMU: bool = False       # Temu: Disabled by default
    ENABLE_SHEIN: bool = True       # Shein: Active
    ENABLE_ALIEXPRESS: bool = True  # AliExpress: Active

settings = Settings()
