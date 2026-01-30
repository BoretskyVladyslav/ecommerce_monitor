import asyncio
import random

class HumanBehavior:
    @staticmethod
    async def run(page):
        await HumanBehavior.random_mouse_movements(page)
        await HumanBehavior.random_scroll(page)
    
    @staticmethod
    async def random_mouse_movements(page, num_moves=None):
        if num_moves is None:
            num_moves = random.randint(3, 7)
        
        viewport = page.viewport_size
        width = viewport['width']
        height = viewport['height']
        
        for _ in range(num_moves):
            x = random.randint(100, width - 100)
            y = random.randint(100, height - 100)
            
            await page.mouse.move(x, y)
            
            await asyncio.sleep(random.uniform(0.1, 0.3))
            
            if random.random() < 0.3:
                await page.mouse.click(x, y)
                await asyncio.sleep(random.uniform(0.05, 0.15))
    
    @staticmethod
    async def random_scroll(page, num_scrolls=None):
        if num_scrolls is None:
            num_scrolls = random.randint(2, 5)
        
        for _ in range(num_scrolls):
            direction = random.choice(['down', 'up'])
            distance = random.randint(100, 400)
            
            if direction == 'down':
                await page.evaluate(f'window.scrollBy(0, {distance})')
            else:
                await page.evaluate(f'window.scrollBy(0, -{distance})')
            
            await asyncio.sleep(random.uniform(0.3, 0.8))
    
    @staticmethod
    async def realistic_typing(page, selector, text, delay_range=(0.05, 0.15)):
        element = await page.query_selector(selector)
        if not element:
            return
        
        await element.click()
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        for char in text:
            await element.type(char)
            await asyncio.sleep(random.uniform(*delay_range))
            
            if random.random() < 0.05:
                await asyncio.sleep(random.uniform(0.3, 0.7))
    
    @staticmethod
    async def random_delay(min_seconds=1, max_seconds=3):
        await asyncio.sleep(random.uniform(min_seconds, max_seconds))
    
    @staticmethod
    async def human_click(page, selector):
        element = await page.query_selector(selector)
        if not element:
            return False
        
        box = await element.bounding_box()
        if not box:
            return False
        
        x = box['x'] + random.uniform(5, box['width'] - 5)
        y = box['y'] + random.uniform(5, box['height'] - 5)
        
        await page.mouse.move(x, y)
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        await page.mouse.click(x, y)
        await asyncio.sleep(random.uniform(0.2, 0.5))
        
        return True
