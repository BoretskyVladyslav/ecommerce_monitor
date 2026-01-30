class SoftBanException(Exception):
    """Raised when a captcha or unusual traffic activity is detected (recoverable)."""
    pass

class HardBanException(Exception):
    """Raised when access is denied or blocked permanently (requires manual intervention)."""
    pass

class ProductNotFoundException(Exception):
    """Raised when the product page returns a 404 or is removed."""
    pass
