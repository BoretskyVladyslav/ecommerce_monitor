class SoftBanException(Exception):
    """Raised when a captcha or unusual traffic activity is detected."""
    pass

class ProductNotFoundException(Exception):
    """Raised when the product page returns a 404 or is removed."""
    pass
