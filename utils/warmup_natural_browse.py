"""
Natural browsing helper for warmup - extracts product links from category pages
"""

async def extract_product_links(page, max_links=15):
    """
    Extract product links from current page (works for Shein category pages)
    
    Args:
        page: Playwright page object
        max_links: Maximum number of links to extract
        
    Returns:
        List of product URLs
    """
    try:
        product_links = await page.evaluate("""
            (maxLinks) => {
                const links = [];
                // Common Shein product link patterns
                const selectors = [
                    'a[href*="/p-"]',           // Product detail pages
                    'a.S-product-item__link',   // Product item links
                    'a[href*=".html"]',         // HTML product pages
                    '.product-card a',          // Generic product cards
                ];
                
                for (const selector of selectors) {
                    const elements = document.querySelectorAll(selector);
                    for (const el of elements) {
                        const href = el.getAttribute('href');
                        if (href && href.includes('-p-') && !links.includes(href)) {
                            // Make absolute URL
                            const url = href.startsWith('http') ? href : new URL(href, window.location.origin).href;
                            links.push(url);
                        }
                    }
                    if (links.length >= maxLinks) break;
                }
                return links.slice(0, maxLinks);
            }
        """, max_links)
        
        return product_links if product_links else []
    except Exception as e:
        return []
