from playwright.async_api import Page
from parsers.amazon import AmazonParser
from parsers.temu import TemuParser
from parsers.shein import SheinParser
from parsers.aliexpress import AliExpressParser
from parsers.base import BaseParser

# Mapping of domain keywords to Parser Classes
PARSER_MAP = {
    "amazon": AmazonParser,
    "temu": TemuParser,
    "shein": SheinParser,
    "aliexpress": AliExpressParser,
}

def get_parser_for_url(url: str, page: Page) -> BaseParser:
    """
    Returns the appropriate parser instance based on the URL.
    Defaults to specific parsers if keyword matched, else strictly None or Generic (not impl).
    """
    url_lower = url.lower()
    
    for key, output_class in PARSER_MAP.items():
        if key in url_lower:
            return output_class(page)
            
    # Raise error or return BaseParser?
    # For now, if we don't have a parser, we can't reliably check stock.
    # Return BaseParser but it doesn't have a 'parse' method with logic.
    # So we raise NotImplementedError or similar behavior.
    raise ValueError(f"No parser found for URL: {url}")
