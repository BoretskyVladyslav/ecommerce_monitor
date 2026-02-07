from parsers.base import BaseParser
from parsers.exceptions import SoftBanException, HardBanException
import asyncio
import random
import json
import re

class SheinParser(BaseParser):
    # BAN_TRIGGERS removed - using CaptchaDetector in BaseParser

    async def check_for_captcha(self):
        """
        🔥 WORK MODE: Immediately trigger warmup instead of solving in the main flow.
        """
        from utils.captcha_detector import captcha_detector
        is_captcha = await captcha_detector.quick_check(self.page, self.marketplace)
        if is_captcha:
            self.logger.warning(f"🚫 Captcha detected on {self.marketplace}! Yielding to Warmup...")
            raise SoftBanException(f"Captcha detected on {self.marketplace} during work process")

    async def check_for_ban(self):
        """
        Alias for check_for_captcha (for backward compatibility).
        """
        await self.check_for_captcha()
    
    async def close_popups(self):
        """
        Closes mobile popups and banners on Shein.
        Uses CSS selectors with classes and data attributes (language-independent).
        """
        popup_selectors = [
            # Close icons by class
            "i.iconfont-close",
            ".iconfont-close",
            ".she-close",
            
            # Close buttons by role/attribute
            "button[aria-label*='lose']",  # Catches "Close", "close", etc.
            "button[data-v-*][class*='close']",
            
            # Dialog and modal close buttons
            ".dialog-header-v2__close-btn",
            ".popup-dialog-couponPackage .close-btn",
            ".c-coupon-box .iconfont-close",
            ".popup-close",
            ".modal-close",
            "[class*='dialog-close']",
            "[class*='popup-close']",
            
            # Newsletter/coupon popups
            "[data-v-acc1714b] .close-btn",
            ".sui-modal__close-btn",
            ".she-modal-close",
            
            # Generic close patterns
            "[class*='close-icon']",
            "[class*='closeBtn']",
        ]
        
        for selector in popup_selectors:
            try:
                locator = self.page.locator(selector)
                
                # Try to click if visible (short timeout)
                if await locator.is_visible(timeout=500):
                    await locator.click(timeout=1000)
                    self.logger.info(f"✅ Closed popup: {selector}")
                    await asyncio.sleep(0.3)  # Reduced delay
            except:
                continue
    
    async def get_availability_from_js(self):
        """
        Витягує повну матрицю залишків (колір + розмір) напряму з JS-об'єкта сторінки.
        Це на 100% надійніше та швидше, ніж клікати по кнопках.
        Не залежить від мови інтерфейсу.
        """
        try:
            self.logger.info("🔍 Attempting to extract data from JavaScript objects...")
            self.logger.info("⏳ Waiting for window.productIntroData to load...")
            
            # 🔥 WAIT for JSON data to load (up to 3 seconds)
            js_data = None
            for attempt in range(6):  # 6 attempts * 0.5s = 3 seconds max
                js_data = await self.page.evaluate("""
                    () => {
                        // Пробуємо різні можливі назви об'єктів на сторінці
                        const data = window.productIntroData || window.gbProductIntroData || window.__INITIAL_STATE__?.product;
                        if (!data) return null;
                        
                        // Отримуємо основну інформацію про товари (SKU)
                        const skuList = data.mainStock?.skuList || data.detail?.skuList || [];
                        const attrList = data.attrSizeList?.sale_attr_list || data.detail?.sale_attr_list || [];
                        
                        if (skuList.length === 0) return null;
                        
                        // Створюємо мапу для швидкого пошуку назв атрибутів
                        const attrMap = {};
                        attrList.forEach(attr => {
                            attr.attr_value_list?.forEach(val => {
                                attrMap[val.attr_value_id] = {
                                    name: val.attr_value_name || val.attr_value,
                                    type: attr.attr_name_en || attr.attr_name || 'unknown'
                                };
                            });
                        });
                        
                        return skuList.map(sku => ({
                            sku_id: sku.sku_id || sku.skuId,
                            stock: parseInt(sku.inventory || sku.stock || 0),
                            // Витягуємо ID атрибутів
                            attributes: sku.skusV2Attributes || sku.sku_sale_attr || [],
                            // Зберігаємо мапу для подальшого розшифровування
                            _attrMap: attrMap
                        }));
                    }
                """)
                
                if js_data and len(js_data) > 0:
                    self.logger.info(f"✅ JSON data loaded on attempt {attempt + 1}")
                    break
                
                await asyncio.sleep(0.5)
            
            if not js_data or len(js_data) == 0:
                # 🔥 If JS data missing, check for captcha before giving up
                await self.check_for_captcha()
                self.logger.info("❌ No JSON data found in window objects")
                return None
            
            self.logger.info(f"✅ Found {len(js_data)} SKU variants in JSON")
            
            # 🔥 BUILD VARIANT MATRIX as {(color, size): status}
            variant_matrix = {}
            
            for item in js_data:
                try:
                    attr_map = item.get('_attrMap', {})
                    attributes = item.get('attributes', [])
                    
                    # Розшифровуємо атрибути за допомогою мапи
                    color = "Default"
                    size = "One Size"
                    
                    for attr in attributes:
                        # attr може бути dict з attr_id або просто ID
                        attr_id = attr.get('attr_value_id') or attr.get('attr_id') or str(attr)
                        
                        if str(attr_id) in attr_map:
                            attr_info = attr_map[str(attr_id)]
                            attr_type = attr_info.get('type', '').lower()
                            attr_name = attr_info.get('name', '')
                            
                            # Визначаємо тип атрибуту (колір або розмір)
                            if 'color' in attr_type or 'colour' in attr_type:
                                color = attr_name
                            elif 'size' in attr_type:
                                size = attr_name
                            else:
                                # Якщо тип невідомий, пробуємо здогадатися
                                # Розміри зазвичай короткі (S, M, L, XL, 38, 40)
                                if len(attr_name) <= 5 and not color.startswith('Color_'):
                                    size = attr_name
                                else:
                                    color = attr_name
                    
                    stock = item.get('stock', 0)
                    # 0 = Active (In Stock), 2 = Out of Stock (DB standard)
                    status = 0 if stock > 0 else 2
                    
                    # Store in matrix with tuple key
                    variant_matrix[(color, size)] = status
                    
                    self.logger.debug(f"  {color} / {size}: {'✅ In Stock' if stock > 0 else '❌ OOS'} (qty: {stock})")
                    
                except Exception as e:
                    self.logger.warning(f"Error processing SKU item: {e}")
                    continue
            
            if len(variant_matrix) > 0:
                self.logger.info(f"✅ Successfully built variant matrix with {len(variant_matrix)} combinations")
                return variant_matrix
            
            return None
            
        except Exception as e:
            self.logger.warning(f"⚠️ Failed to extract JSON data: {e}")
            return None

    async def get_availability_from_json_ld(self):
        """
        Parses application/ld+json using Regex on raw HTML (Strategy: "Easy").
        Bypasses locator issues and works even if overlays are present.
        """
        try:
            self.logger.info("🔍 Parsing LD+JSON for availability (Regex method)...")
            content = await self.page.content()
            
            # Find JSON-LD block using ROBUST regex
            # Allow:
            # - type='...' or type="..."
            # - spaces around attributes
            # - other attributes in the script tag
            pattern = r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>'
            json_ld_matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            
            if not json_ld_matches:
                self.logger.warning("⚠️ Regex found no matches. Trying Playwright locator fallback...")
                try:
                    # Fallback: Playwright DOM access (Reliable if regex fails due to whitespace/formatting)
                    json_ld_matches = await self.page.locator('script[type="application/ld+json"]').all_inner_texts()
                except: 
                    pass
            
            if not json_ld_matches:
                # 🔥 If JSON-LD missing, check for captcha
                await self.check_for_captcha()
                self.logger.warning("❌ No JSON-LD scripts found via Regex OR Locator")
                return None
            
            variant_matrix = {}
            current_page_color = None
            
            # Try to get color from DOM as backup
            try:
                color_label = await self.page.locator(".product-intro__color-title, .product-intro__color-radio.selected").first.text_content()
                if color_label:
                    current_page_color = color_label.replace("Color:", "").strip()
            except: pass

            self.logger.info(f"🕵️ JSON INSPECT: 🔍 Found {len(json_ld_matches)} JSON-LD blocks.")

            for i, script_content in enumerate(json_ld_matches):
                try:
                    data = json.loads(script_content)
                    if isinstance(data, dict):
                         type_val = data.get("@type", "NoType")
                    elif isinstance(data, list) and len(data) > 0:
                         type_val = f"List (first: {data[0].get('@type', 'NoType')})"
                    else:
                         type_val = "Unknown"

                    self.logger.info(f"   Block #{i+1}: Type='{type_val}'")
                    
                    # Find ProductGroup
                    product_group = None
                    if isinstance(data, list):
                         for item in data:
                             if item.get("@type") == "ProductGroup":
                                 product_group = item
                                 break
                    elif isinstance(data, dict) and data.get("@type") == "ProductGroup":
                        product_group = data
                        
                    if not product_group:
                        self.logger.info(f"   ⚠️ Block #{i+1}: Not a ProductGroup. Skipping.")
                        continue # Try next script

                    if "hasVariant" not in product_group:
                        self.logger.info(f"   ⚠️ Block #{i+1}: ProductGroup found but NO VARIANTS. Skipping.")
                        continue # Try next script

                    # Extract Color for the group
                    group_color = product_group.get("color")
                    if not group_color:
                        group_color = current_page_color
                        
                    # ID: Logging for "Inspector"
                    self.logger.info(f"🕵️ JSON INSPECT: Found Group. Main Color: '{group_color}'")
                    
                    # 🔥 DEBUG: DUMP FULL JSON TO CONSOLE
                    print("\n" + "="*50)
                    print(f"🕵️ JSON DUMP FOR BLOCK #{i+1}:")
                    print(json.dumps(product_group, indent=2))
                    print("="*50 + "\n")

                    # Process Variants

                    # Process Variants
                    for variant in product_group["hasVariant"]:
                        size = variant.get("size")
                        if not size: continue
                        
                        # Variant specific color (rare but possible)
                        # If not present, use group color
                        v_color = variant.get("color", group_color)
                        
                        if not v_color: continue # Can't map
                        
                        offers = variant.get("offers", {})
                        availability = offers.get("availability", "")
                        
                        # 0 = Active (In Stock), 2 = Out of Stock
                        # Note: Shein schema uses "InStock" or "OutOfStock"
                        is_in_stock = 0 if "InStock" in availability else 2
                        
                        # --- LOGGING FOR DEBUG ---
                        icon = "✅" if is_in_stock == 0 else "❌"
                        self.logger.info(f"   👉 {icon} JSON: Color='{v_color}' | Size='{size}' | Raw='{availability}' -> Status={is_in_stock}")
                        # -------------------------
                        variant_matrix[(v_color, size)] = is_in_stock
                
                except: continue

            if len(variant_matrix) > 0:
                self.logger.info(f"✅ Extracted {len(variant_matrix)} variants from JSON-LD")
                
                # 🔥 FINAL CHECK: Even if we got data, check if there's a captcha overlay!
                # This prevents "Lazy Bans" where data is present but actions are blocked.
                await self.check_for_captcha()
                
                return variant_matrix
            else:
                return None

        except Exception as e:
            self.logger.error(f"❌ Error in JSON-LD parsing: {e}")
            return None

    
    async def parse(self, target_color=None, target_size=None):
        """
        Parses Shein mobile page for availability using Color + Size logic.
        Uses CSS selectors with technical attributes (language-independent).
        """
        try:
            self.logger.info("SHEIN PARSER LOADED V5 (Targeted Color+Size Matching)")
            
            # Log target variant if specified
            if target_color or target_size:
                self.logger.info(f"🎯 Target Variant: Color='{target_color}' / Size='{target_size}'")
            else:
                self.logger.info("🔍 Checking general availability (any variant)")  
            
            # Step 1: Check for ban/captcha FIRST (Shein-specific)
            await self.check_for_ban()
            
            # Step 1.1: Check for generic captchas (from BaseParser)
            await self.check_for_captcha()
            
            # Step 1.5: Check for redirects (Login or Risk)
            current_url = self.page.url
            
            # Check for Login Redirect (Crawler detected)
            if "/user/auth/login" in current_url:
                self.logger.warning(f"🚫 Shein Login Redirect detected (Crawler Sign): {current_url}")
                raise SoftBanException("Shein Login/Crawler Redirect detected")

            if "/risk/challenge" in current_url:
                self.logger.warning(f"🚫 Shein Risk Challenge detected: {current_url}")
                # 🔥 Don't try to solve - immediately trigger warmup
                raise SoftBanException("Risk Challenge detected - triggering warmup")
            
            # Step 2: Close any popups
            await self.close_popups()
            
            # Step 3: Wait for content to load (SMART WAIT)
            # Wait for meaningful content (e.g. product intro) while checking for captcha
            try:
                await self.wait_for_captcha_or_element(".product-intro", timeout=6)
            except SoftBanException:
                raise
            except:
                pass # Timeout is fine, just continue
                
            await asyncio.sleep(random.uniform(1.0, 2.0)) # Extra human pause
            
            # Step 4: Check for error pages using CSS selectors (avoid text=)
            error_page_selectors = [
                ".error-page",
                ".page-not-found",
                "[class*='error']",
            ]
            
            for selector in error_page_selectors:
                try:
                    locator = self.page.locator(selector)
                    if await locator.is_visible(timeout=500):
                        self.logger.info("Shein: Error page detected.")
                        return 0
                except:
                    continue
            
            # Step 5: PRIORITY - Extract data from JSON-LD (Schema.org)
            # This is the new robust method (User Request)
            availability_result = await self.get_availability_from_json_ld()
            
            # --- INTELLIGENT FALLBACK ---
            # If JSON-LD found something, check if it contains our TARGET variant
            matched_status = None
            if availability_result and isinstance(availability_result, dict):
                
                # Check for EXACT match
                if target_color or target_size:
                     key = (target_color, target_size)
                     
                     # Direct match
                     if key in availability_result:
                         matched_status = availability_result[key]
                         self.logger.info(f"✅ JSON-LD Hit: Found exact match for {target_color}/{target_size}")
                     else:
                         # Case-insensitive match check
                         for (c, s), st in availability_result.items():
                             c_match = c.lower().strip() == target_color.lower().strip() if target_color else True
                             
                             if target_size:
                                 s_item = s.lower().strip()
                                 s_target = target_size.lower().strip()
                                 if len(s_target) <= 3 or len(s_item) <= 3:
                                     s_match = s_item == s_target
                                 else:
                                     s_match = s_item == s_target or s_target in s_item
                             else:
                                 s_match = True
                                 
                             if c_match and s_match:
                                 matched_status = st
                                 self.logger.info(f"✅ JSON-LD Hit (Fuzzy): Found match for {c}/{s}")
                                 break
                
                if matched_status is not None:
                    return matched_status
                else:
                    self.logger.warning(f"❌ Target variant {target_color}/{target_size} NOT found in JSON-LD. Page might be wrong color.")
                    # Force fallback to DOM parsing because JSON-LD only has current page color data
                    availability_result = None 

            
            # If JSON-LD failed OR didn't have our target variant, fallback to DOM parsing
            if matched_status is None:
                self.logger.info("📋 Falling back to DOM parsing (legacy method) to switch color...")
                # Pass target_color to optimize DOM clicking (only click correct color)
                availability_result = await self.get_product_availability(target_color=target_color)
            
            # If we got structured data with color/size combos, analyze it
            # 🔥 NEW: Check if it's a dict (variant_matrix) or list (legacy)
            if isinstance(availability_result, dict) and len(availability_result) > 0:
                # === SMART MATCHING WITH DICT (OPTIMIZED) ===
                if target_color or target_size:
                    self.logger.info(f"🔍 Searching for exact match: {target_color} / {target_size}")
                    
                    # Try direct lookup first
                    key = (target_color, target_size)
                    if key in availability_result:
                        status = availability_result[key]
                        self.logger.info(f"✅ Found exact match: {target_color} / {target_size} - {'IN STOCK' if status else 'SOLD OUT'}")
                        return status
                    
                    # Try case-insensitive match
                    for (color, size), status in availability_result.items():
                        color_match = target_color and color.lower().strip() == target_color.lower().strip() if target_color else True
                        
                        if target_size:
                            s_item = size.lower().strip()
                            s_target = target_size.lower().strip()
                            # Strict match for short sizes
                            if len(s_target) <= 3 or len(s_item) <= 3:
                                size_match = s_item == s_target
                            else:
                                size_match = s_item == s_target or s_target in s_item
                        else:
                            size_match = True

                        if color_match and size_match:
                            self.logger.info(f"✅ Found match: {color} / {size} - {'IN STOCK' if status else 'SOLD OUT'}")
                            return status
                    
                    self.logger.warning(f"❌ Combination '{target_color}' / '{target_size}' not found")
                    variants_str = ", ".join([f"{c}/{s}" for c, s in list(availability_result.keys())[:5]])
                    self.logger.info(f"Available variants (first 5): {variants_str}...")
                    return 0  # Not found = Sold Out
                else:
                    # No specific variant requested - check if ANY is in stock
                    any_in_stock = any(status == 1 for status in availability_result.values())
                    self.logger.info(f"✅ General availability: {'IN STOCK' if any_in_stock else 'SOLD OUT'}")
                    return 1 if any_in_stock else 0
                    
            elif isinstance(availability_result, list) and len(availability_result) > 0:
                # === LEGACY SUPPORT: List format (from old get_product_availability) ===
                if target_color or target_size:
                    self.logger.info(f"🔍 Searching for exact match: {target_color} / {target_size}")
                    match = None
                    
                    for item in availability_result:
                        color_match = True
                        size_match = True
                        
                        # Check color match (case-insensitive, flexible)
                        if target_color:
                            item_color = item.get('color', '').lower().strip()
                            target_color_lower = target_color.lower().strip()
                            color_match = item_color == target_color_lower or target_color_lower in item_color
                        
                        # Check size match
                        if target_size:
                            item_size = item.get('size', '').lower().strip()  
                            target_size_lower = target_size.lower().strip()
                            
                            # EXACT match for short sizes to avoid S in XS
                            if len(target_size_lower) <= 3 or len(item_size) <= 3:
                                size_match = item_size == target_size_lower
                            else:
                                # Loose match for longer names (e.g. "One Size")
                                size_match = item_size == target_size_lower or target_size_lower in item_size
                        
                        # If both match, we found it
                        if color_match and size_match:
                            match = item
                            break
                    
                    if match:
                        stock_qty = match.get('quantity', 0)
                        in_stock = match.get('in_stock', 0)
                        self.logger.info(f"✅ Found exact match: {match['color']} / {match['size']} - {'IN STOCK' if in_stock else 'SOLD OUT'} (qty: {stock_qty})")
                        return in_stock
                    else:
                        self.logger.warning(f"❌ Combination '{target_color}' / '{target_size}' not found on page")
                        variants_str = ", ".join([f"{item.get('color')}/{item.get('size')}" for item in availability_result[:5]])
                        self.logger.info(f"Available variants (first 5): {variants_str}...")
                        return 0  # Not found = Sold Out
                
                # If no target specified, check if ANY combination is in stock
                else:
                    in_stock_count = sum(1 for item in availability_result if item.get("in_stock") == 1)
                    
                    self.logger.info(f"Shein: Found {len(availability_result)} color+size combinations, {in_stock_count} in stock")
                    
                    # Return 1 if at least one variant is available, else 0
                    return 1 if in_stock_count > 0 else 0
            
            # Fallback: if no variants found, check for general "Sold Out" or "Add to Cart"
            self.logger.info("⚠️ No variants found via JSON or DOM, trying general availability check")
            return await self.check_general_availability()

        except SoftBanException:
            # Re-raise to trigger proxy rotation
            raise
        except Exception as e:
            self.logger.error(f"Error parsing Shein: {e}")
            raise e
    
    async def get_product_availability(self, target_color=None):
        """
        Implements Color + Size logic using CSS selectors and data attributes.
        Returns a list of dict with {color, size, in_stock}.
        
        If target_color is set, it attempts to find and click ONLY that color.
        """
        results = []
        
        try:
            # 1. Get all color containers using CSS selectors
            color_container_selector = ".main-sales-attr__color-container .radio-container, .main-sales-attr__color .radio-container"
            color_elements = await self.page.locator(color_container_selector).all()
            
            if not color_elements:
                self.logger.info("No color variants found, trying to get sizes directly")
                # If no colors, just get available sizes
                return await self.get_sizes_for_current_color(None)
            
            self.logger.info(f"Found {len(color_elements)} color variants")
            
            # 2. Iterate through each color
            found_target = False
            
            for idx, color_element in enumerate(color_elements):
                try:
                    # Get color name from img alt attribute or data attribute
                    color_name = None
                    try:
                        # Try to get from img alt
                        color_img = color_element.locator("img")
                        color_name = await color_img.get_attribute("alt")
                        if not color_name:
                             # Some images use aria-label on the container or similar
                             color_name = await color_element.get_attribute("aria-label")
                    except:
                        pass
                    
                    if not color_name:
                        try:
                            # Try data-attr_value_name
                            color_name = await color_element.get_attribute("data-attr_value_name")
                        except:
                            pass
                    
                    if not color_name:
                        # try to get tooltips if present?
                        try:
                             color_name = await color_element.get_attribute("title")
                        except: pass

                    if not color_name:
                        # Fallback for logging, but useless for targeted matching if not index-based
                        color_name = f"Color_{idx + 1}"
                    
                    # Clean color name
                    color_name = color_name.strip()
                    if "Color:" in color_name:
                        color_name = color_name.replace("Color:", "").strip()

                    # --- FILTER LOGIC ---
                    if target_color:
                        c_match = color_name.lower().strip() == target_color.lower().strip() or target_color.lower() in color_name.lower()
                        if not c_match:
                            # Skip this color if it doesn't match target
                            # self.logger.debug(f"Skipping color {color_name} (looking for {target_color})")
                            continue
                        else:
                            self.logger.info(f"🎯 Found target color button: {color_name}")
                            found_target = True

                    self.logger.info(f"Processing color: {color_name}")
                    
                    # Ensure element is visible/clickable
                    if not await color_element.is_visible():
                         await color_element.scroll_into_view_if_needed()
                    
                    await color_element.click()
                    
                    # 🔥 Human-like wait + Captcha Check
                    # Wait for sizes to appear or refresh
                    try:
                         # We are waiting for sizes to update. We use a dummy timeout with captcha check.
                         await self.wait_for_captcha_or_element(".product-intro__size-radio", timeout=random.uniform(2.0, 3.5))
                    except SoftBanException:
                         raise
                    except: 
                         pass
                    
                    # 3. Get all sizes for this color
                    size_results = await self.get_sizes_for_current_color(color_name)
                    results.extend(size_results)
                    
                    # If we found our target, we can stop after processing it (unless we want to fill matrix? But user wants speed)
                    if target_color and found_target:
                        self.logger.info("✅ Processed target color, stopping scan.")
                        break

                    # 🔥 Human-like pause between colors
                    if idx < len(color_elements) - 1:
                        await asyncio.sleep(random.uniform(1.0, 3.0))
                    
                except Exception as e:
                    self.logger.warning(f"Error processing color {idx}: {e}")
                    continue
            
            if target_color and not found_target:
                 self.logger.warning(f"⚠️ Target color '{target_color}' not found in DOM list. Buttons might be unlabeled or hidden.")
                 # Optional: Do we fallback to full scan? Maybe risky. Let's return what we have (empty)
            
            return results
            
        except Exception as e:
            self.logger.warning(f"Error in get_product_availability: {e}")
            return []
    
    async def get_sizes_for_current_color(self, color_name):
        """
        Gets all size options for the currently selected color.
        Returns list of {color, size, in_stock}.
        """
        size_results = []
        
        try:
            # Find all size radio buttons using CSS selectors
            size_selector = ".product-intro__size-radio, .product-intro__size-choose .product-intro__size-radio"
            size_elements = await self.page.locator(size_selector).all()
            
            if not size_elements:
                self.logger.info(f"No size variants found for color: {color_name}")
                return []
            
            self.logger.info(f"Found {len(size_elements)} size variants for color: {color_name}")
            
            for idx, size_element in enumerate(size_elements):
                try:
                    # Get size name from data attribute
                    size_name = None
                    try:
                        size_name = await size_element.get_attribute("data-attr_value_name")
                    except:
                        pass
                    
                    if not size_name:
                        try:
                            size_name = await size_element.get_attribute("data-size-radio")
                        except:
                            pass
                    
                    if not size_name:
                        # Fallback: try to get text content
                        try:
                            size_name = await size_element.text_content()
                            size_name = size_name.strip() if size_name else None
                        except:
                            pass
                    
                    if not size_name:
                        size_name = f"Size_{idx + 1}"
                    
                    # Check if size is available (not disabled or out-of-stock)
                    is_disabled = False
                    
                    # Method 1: Check for out-of-stock icon
                    try:
                        oos_icon = size_element.locator(".out-of-stock-icon")
                        if await oos_icon.is_visible(timeout=200):
                            is_disabled = True
                    except:
                        pass
                    
                    # Method 2: Check class attribute for disabled/oos markers
                    if not is_disabled:
                        try:
                            class_attr = await size_element.get_attribute("class")
                            if class_attr:
                                is_disabled = "disabled" in class_attr or "is-out-of-stock" in class_attr or "out-of-stock" in class_attr
                        except:
                            pass
                    
                    # Method 3: Check disabled attribute
                    if not is_disabled:
                        try:
                            disabled_attr = await size_element.get_attribute("disabled")
                            is_disabled = disabled_attr is not None
                        except:
                            pass
                    
                    in_stock = 0 if is_disabled else 1
                    
                    size_results.append({
                        "color": color_name,
                        "size": size_name,
                        "in_stock": in_stock
                    })
                    
                    self.logger.debug(f"  Size: {size_name} - {'OOS' if is_disabled else 'Available'}")
                    
                except Exception as e:
                    self.logger.warning(f"Error processing size {idx}: {e}")
                    continue
            
            return size_results
            
        except Exception as e:
            self.logger.warning(f"Error in get_sizes_for_current_color: {e}")
            return []
    
    async def check_general_availability(self):
        """
        Fallback method to check general availability when no variants are found.
        Uses CSS selectors instead of text-based selection where possible.
        """
        try:
            # Check for sold out indicators using classes
            sold_out_class_selectors = [
                ".goods-sold-out",
                ".product-intro__sold-out",
                "[class*='sold-out']"
            ]
            
            for selector in sold_out_class_selectors:
                try:
                    locator = self.page.locator(selector)
                    if await locator.is_visible(timeout=500):
                        self.logger.info("Shein: Product is Sold Out (general check).")
                        return 0
                except:
                    continue
            
            # Check for "Add to Cart" / "Add to Bag" button using classes
            add_to_bag_class_selectors = [
                ".bottom-action__btn",
                ".add-to-bag",
                ".she-btn-black",
                "[class*='add-to-cart']",
                "[class*='add-to-bag']"
            ]
            
            for selector in add_to_bag_class_selectors:
                try:
                    locator = self.page.locator(selector)
                    if await locator.is_visible(timeout=500):
                        # Check if disabled
                        is_disabled = await locator.get_attribute("disabled")
                        if is_disabled is not None:
                            self.logger.info("Shein: 'Add to Bag' button is disabled.")
                            return 0
                        
                        self.logger.info("Shein: Product is In Stock (general check).")
                        return 1
                except:
                    continue
            
            
            # No clear indicators found
            self.logger.info("Shein: No status indicators found. Assuming OOS or Error.")
            return 0
            
        except Exception as e:
            self.logger.warning(f"Error in check_general_availability: {e}")
            return 0

    async def get_dom_matrix(self, target_color):
        """
        DOM FALLBACK: Robustly finds color button and scrapes ALL sizes.
        Matches legacy logic for finding colors (e.g. 'Blue' -> 'Navy Blue').
        """
        try:
            # 🔥 Start with Captcha check
            await self.check_for_captcha()

            self.logger.info(f"🧱 DOM MATRIX: Switching to color '{target_color}'...")
            
            # 1. Пошук елементів кольору (Legacy robust selectors + New ones)
            selectors = [
                ".main-sales-attr__color-container .radio-container", # Найбільш надійний (Legacy)
                ".main-sales-attr__color .radio-container",
                ".product-intro__color-radio", 
                ".product-intro__color-block",
                ".goods-img-item",
                ".color-inner",
                "div[aria-label]"
            ]
            
            color_elements = []
            for sel in selectors:
                elements = await self.page.locator(sel).all()
                if elements:
                    color_elements = elements
                    break
            
            if not color_elements:
                # 🔥 Check for captcha if no elements found
                await self.check_for_captcha()
                self.logger.warning("❌ DOM MATRIX: No color elements found in DOM.")
                return None

            # 2. Пошук потрібної кнопки (Нечіткий пошук + перевірка ВСІХ атрибутів)
            target_btn = None
            found_text = ""
            
            for el in color_elements:
                # Збираємо текст з усіх можливих джерел (як у legacy get_product_availability)
                text_sources = []
                
                # 1. Alt з картинки
                try:
                    img_alt = await el.locator("img").get_attribute("alt")
                    if img_alt: text_sources.append(img_alt)
                except: pass
                
                # 2. Data attributes (найчастіше тут ховається правильна назва)
                try:
                    data_name = await el.get_attribute("data-attr_value_name")
                    if data_name: text_sources.append(data_name)
                except: pass
                
                # 3. Aria & Title & InnerText
                text_sources.append(await el.get_attribute("aria-label") or "")
                text_sources.append(await el.get_attribute("title") or "")
                text_sources.append(await el.inner_text() or "")
                
                # Об'єднуємо все в один рядок для пошуку
                full_text = " ".join([t for t in text_sources if t]).lower()
                
                # Очистка (видалення сміття типу "Color:")
                full_text = full_text.replace("color:", "").strip()
                
                # Перевірка входження (наприклад "blue" in "navy blue")
                if target_color.lower() in full_text:
                    target_btn = el
                    found_text = full_text
                    break
            
            if not target_btn:
                self.logger.warning(f"❌ DOM MATRIX: Button for '{target_color}' not found among {len(color_elements)} options.")
                return None

            # 3. Клік і очікування (Human-like)
            self.logger.info(f"✅ DOM MATRIX: Clicking target matching '{target_color}'...")
            
            # Scroll if needed
            if not await target_btn.is_visible():
                await target_btn.scroll_into_view_if_needed()
                await asyncio.sleep(random.uniform(0.5, 1.0))

            # Human Interaction Sequence:
            # 1. Hover
            await target_btn.hover()
            await asyncio.sleep(random.uniform(0.3, 0.7))
            
            # 2. Click
            await target_btn.click()
            
            # Smart Wait: Чекаємо поки прогрузяться розміри
            # (Можна зробити розумніше очікування, але sleep надійніший при динаміці)
            await asyncio.sleep(random.uniform(2.5, 4.0)) 
            
            # 🔥 Check for Captcha after interaction
            await self.check_for_captcha() 

            # 4. Зчитування матриці розмірів
            matrix = {}
            
            # Шукаємо кнопки розмірів (Legacy + New selectors)
            size_selectors = [
                ".product-intro__size-radio", 
                ".product-intro__size-btn", 
                ".size-item",
                ".product-intro__size-choose .product-intro__size-radio" # Legacy
            ]
            
            size_elements = []
            for sel in size_selectors:
                els = await self.page.locator(sel).all()
                if els:
                    size_elements = els
                    break

            if not size_elements:
                 self.logger.warning("❌ DOM MATRIX: No size elements found after click.")
                 return None
            
            self.logger.info(f"   🔘 Scanning {len(size_elements)} sizes...")
            
            for size_el in size_elements:
                # Спробуємо дістати ім'я розміру різними способами (Legacy logic)
                size_name = await size_el.get_attribute("data-attr_value_name")
                if not size_name:
                    size_name = await size_el.get_attribute("data-size-radio")
                if not size_name:
                    size_name = await size_el.inner_text()
                
                if not size_name: continue
                
                class_attr = await size_el.get_attribute("class") or ""
                
                # Логіка OOS (Out of Stock)
                is_oos = False
                
                # Перевірка класів
                if "disabled" in class_attr.lower() or "out-of-stock" in class_attr.lower():
                    is_oos = True
                
                # Перевірка атрибуту disabled
                if not is_oos:
                     if await size_el.get_attribute("disabled"):
                         is_oos = True

                # Статус: 0 = Active, 2 = OOS
                status = 2 if is_oos else 0
                
                # Чистимо назву (наприклад "S (4)" -> "S")
                clean_size = size_name.split('(')[0].strip()
                
                # Ключ матриці: (Цільовий колір, Знайдений розмір)
                # Використовуємо target_color, щоб MonitorEngine міг легко знайти цей запис
                matrix[(target_color, clean_size)] = status
                
                # Лог для перевірки
                icon = "✅" if status == 0 else "❌"
                self.logger.info(f"      👉 {clean_size}: {icon}")
                
            return matrix

        except Exception as e:
            self.logger.error(f"DOM Matrix error: {e}")
            return None
