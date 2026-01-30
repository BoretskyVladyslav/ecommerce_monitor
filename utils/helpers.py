from urllib.parse import urlparse

def detect_marketplace(url: str) -> str:
    """
    Detects marketplace type from URL.
    """
    domain = urlparse(url).netloc.lower()
    
    if 'amazon' in domain:
        return 'amazon'
    elif 'shein' in domain:
        return 'shein'
    elif 'temu' in domain:
        return 'temu'
    elif 'aliexpress' in domain:
        return 'aliexpress'
    else:
        return 'unknown'
