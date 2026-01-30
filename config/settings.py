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
    HEADLESS: bool = True  

    PROXY_URL: str = None

settings = Settings()
