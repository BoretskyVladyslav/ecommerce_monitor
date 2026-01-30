import asyncio
import random
import math
from playwright.async_api import Page
from config.logger import logging

logger = logging.getLogger("HumanTools")

class HumanTools:
    def __init__(self, page: Page):
        self.page = page

    async def random_delay(self, min_seconds: float = 2.0, max_seconds: float = 5.0):
        """Waits for a random amount of time."""
        delay = random.uniform(min_seconds, max_seconds)
        # logger.debug(f"Sleeping for {delay:.2f}s")
        await asyncio.sleep(delay)

    async def natural_mouse_move(self, target_x: float, target_y: float):
        """
        Moves the mouse to (target_x, target_y) using a Cubic Bezier curve 
        to simulate human hand movement.
        """
        try:
            # Get current mouse position logic (simulated)
            # Playwright doesn't easily give "current" mouse pos without tracking.
            # We assume starting from a random point or the last known element.
            # For this implementation, we will move "from" where the mouse effectively is,
            # but since we can't query it easily, we just animate the steps.
            
            # Actually Playwright's mouse.move executes a move.
            # To do steps, we call mouse.move multiple times.
            
            # Let's get viewport size to ensure we stay in bounds or generate "start" if needed.
            # Since we can't get current pos easily, we'll assume a "virtual" start 
            # or just skip the exact start point and focus on the curve approaches.
            
            # A better approach with Playwright: use steps in mouse.move?
            # page.mouse.move(x, y, steps=20) does linear interpolation.
            # We want non-linear.
            
            # We will start from a random position slightly off-screen or center if unknown,
            # BUT better is to just pick a point near the current focus or 0,0 for simplicity
            # if we can't track it. 
            # However, simpler for "Human Emulation" is to just break the path into segments.
            
            # Let's use a simplified approach:
            # 1. Get approximate current position (or just standard move if tracking is hard).
            # 2. Since we lack 'current_pos', we will focus on 'steps' parameter of playwright 
            #    modified by some jitter, OR we generate a path.
            
            # Implementing explicit Bezier path:
            # We need a start point. Let's assume start is (0,0) or center if it's the first move,
            # OR we just let Playwright handle the linear move but with "steps".
            # The USER requested "Curved paths".
            
            # TRICK: We can move the mouse relative to an element. 
            # But here we are given absolute coords or logic.
            
            # Let's try to assume we just want to move TO target_x, target_y
            # We can define a "start" based on a previous move if we tracked it,
            # but HumanTools instance might be new.
            
            # Fallback: Just move linearly if we don't know start? 
            # No, user wants curve. Let's assume start is (0,0) or randomly top-left.
            start_x = random.randint(0, 100)
            start_y = random.randint(0, 100)
            
            # Generate Control Points
            control1_x = start_x + random.randint(-100, 100)
            control1_y = start_y + random.randint(-100, 100)
            control2_x = target_x + random.randint(-100, 100)
            control2_y = target_y + random.randint(-100, 100)
            
            steps = 25
            for i in range(steps):
                t = i / steps
                # Cubic Bezier Formula
                # B(t) = (1-t)^3*P0 + 3*(1-t)^2*t*P1 + 3*(1-t)*t^2*P2 + t^3*P3
                
                cx = (1-t)**3 * start_x + \
                     3 * (1-t)**2 * t * control1_x + \
                     3 * (1-t) * t**2 * control2_x + \
                     t**3 * target_x
                     
                cy = (1-t)**3 * start_y + \
                     3 * (1-t)**2 * t * control1_y + \
                     3 * (1-t) * t**2 * control2_y + \
                     t**3 * target_y
                
                await self.page.mouse.move(cx, cy)
                await asyncio.sleep(random.uniform(0.01, 0.03))
                
            # Final accurate move
            await self.page.mouse.move(target_x, target_y)
            
        except Exception as e:
            logger.warning(f"Mouse move failed: {e}")
            # Fallback
            await self.page.mouse.move(target_x, target_y)

    async def warm_up(self, marketplace: str):
        """
        Simulates warm-up activity:
        1. Go to home page.
        2. Type random search? Or just scroll/click random item.
        3. Human pauses.
        """
        logger.info(f"Warming up for {marketplace}...")
        
        home_urls = {
            'amazon': 'https://www.amazon.com',
            'shein': 'https://www.shein.com',
            'temu': 'https://www.temu.com',
            'aliexpress': 'https://www.aliexpress.com'
        }
        
        url = home_urls.get(marketplace, 'https://www.google.com')
        
        try:
            # 1. Goto Home
            await self.page.goto(url, wait_until="domcontentloaded")
            await self.random_delay(2, 4)
            
            # 2. Scroll a bit
            await self.page.mouse.wheel(0, random.randint(300, 700))
            await self.random_delay(1, 3)
            
            # 3. Move mouse naturally to random point (center-ish)
            await self.natural_mouse_move(random.randint(300, 800), random.randint(300, 800))
            
            # 4. Try to find a product image and click it (Fake browsing)
            # Generic approach: look for typical product container tags or just random 'a' or 'img'
            # This is "best effort" for generic sites
            potential_links = self.page.locator("a[href]")
            count = await potential_links.count()
            
            if count > 0:
                # Click a random link from the first few
                idx = random.randint(0, min(count - 1, 10))
                item = potential_links.nth(idx)
                if await item.is_visible():
                    box = await item.bounding_box()
                    if box:
                        # Move to it first
                        await self.natural_mouse_move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                        await asyncio.sleep(random.uniform(0.5, 1.0))
                        # Click
                        # await item.click() # Clicking might navigate away, which is fine for warmup
                        # For now, maybe just hover is safer to not get stuck in navigation loops?
                        # User said "Open random left product". So we should click.
                        
                        logger.info("Warmup: Clicking random product/link")
                        await item.click()
                        await self.random_delay(3, 6)
                        
                        # Go back? Or just proceed to target from here?
                        # Usually better to start target navigation fresh, 
                        # but having history in tab is good.
            
            logger.info("Warmup complete.")
            
        except Exception as e:
            logger.warning(f"Warmup failed: {e}")
