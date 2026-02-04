"""
Slider Solver with Human-like Behavior
Реалізує реалістичні рухи мишею (криві Бєзьє, зміна швидкості, тремтіння)
для проходження слайдер-капчі (Slider, Puzzle, GeeTest).
"""
import asyncio
import random
import time
import math
import numpy as np
from playwright.async_api import Page, ElementHandle
from config.logger import setup_logger

logger = setup_logger("SliderSolver")

class SliderSolver:
    """
    Клас для реалістичного перетягування слайдера.
    Використовує криві Бєзьє 4-го порядку для генерації шляху.
    """
    
    def __init__(self):
        pass

    def _ease_out_quad(self, t):
        """Easing function (швидкий початок, повільний кінець)"""
        return t * (2 - t)

    def _ease_in_out_cubic(self, t):
        return 4 * t * t * t if t < 0.5 else 1 - pow(-2 * t + 2, 3) / 2

    def _get_bezier_point(self, t, p0, p1, p2, p3):
        """Розрахунок точки на кривій Бєзьє (Cubic)"""
        u = 1 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t
        
        x = uuu * p0['x'] + 3 * uu * t * p1['x'] + 3 * u * tt * p2['x'] + ttt * p3['x']
        y = uuu * p0['y'] + 3 * uu * t * p1['y'] + 3 * u * tt * p2['y'] + ttt * p3['y']
        
        return {'x': x, 'y': y}

    def _generate_path(self, start, end, steps=50):
        """
        Генерує шлях миші між двома точками використовуючи криві Бєзьє.
        Додає "шум" та відхилення по Y.
        """
        path = []
        
        # Контрольні точки для кривої
        # p0 - старт
        # p3 - кінець
        # p1, p2 - проміжні точки для вигину
        
        distance = end['x'] - start['x']
        
        # Випадкове відхилення по Y (рука тремтить/йде не ідеально рівно)
        y_variance = random.randint(-10, 10)
        
        p0 = start
        p1 = {
            'x': start['x'] + distance * random.uniform(0.2, 0.4),
            'y': start['y'] + random.randint(-20, 20)
        }
        p2 = {
            'x': start['x'] + distance * random.uniform(0.6, 0.8),
            'y': start['y'] + random.randint(-20, 20)
        }
        p3 = end
        
        # Генеруємо точки
        for i in range(steps + 1):
            t = i / steps
            # Застосовуємо easing до t, щоб рух був нелінійним за часом
            # t_eased = self._ease_out_quad(t)
            point = self._get_bezier_point(t, p0, p1, p2, p3)
            
            # Додаємо мікро-тремтіння
            if i > 0 and i < steps:
                point['x'] += random.uniform(-1, 1)
                point['y'] += random.uniform(-1, 1)
            
            path.append(point)
            
        return path

    async def slide(self, page: Page, slider_handle: ElementHandle, x_offset: int):
        """
        Виконує перетягування слайдера на задану відстань.
        
        Args:
            page: Playwright Page object
            slider_handle: ElementHandle кнопки слайдера
            x_offset: Відстань руху по X (пікселі)
        """
        box = await slider_handle.bounding_box()
        if not box:
            logger.error("❌ Cannot get bounding box for slider")
            return False
            
        # Початкова точка (центр кнопки слайдера)
        start_x = box['x'] + box['width'] / 2
        start_y = box['y'] + box['height'] / 2
        
        # Кінцева точка
        # Іноді трохи перетягуємо або недотягуємо (overshoot), потім коригуємо
        target_x = start_x + x_offset
        true_target_x = target_x
        
        # Overshoot logic (симуляція людської помилки)
        should_overshoot = random.random() < 0.7
        overshoot_amount = 0
        if should_overshoot:
            overshoot_amount = random.randint(5, 20)
            target_x += overshoot_amount
        
        end_y = start_y + random.randint(-5, 5) # Трохи зміщуємо Y в кінці
        
        # 1. Move to start
        logger.info(f"🖱️ Moving to start: {start_x}, {start_y}")
        await page.mouse.move(start_x, start_y, steps=5)
        await page.mouse.down()
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        # 2. Drag to target (with overshoot)
        await asyncio.sleep(random.uniform(0.05, 0.1)) # Give time for event listeners
        
        steps = random.randint(30, 60)
        path = self._generate_path(
            {'x': start_x, 'y': start_y},
            {'x': target_x, 'y': end_y},
            steps=steps
        )
        
        logger.info(f"🎢 Dragging slider to offset {x_offset} (Overshoot: {overshoot_amount})...")
        
        for point in path:
            await page.mouse.move(point['x'], point['y'])
            # Пауза між кроками (змінна)
            await asyncio.sleep(random.uniform(0.001, 0.015))
        
        # 3. Correction (якщо був overshoot)
        if should_overshoot:
            await asyncio.sleep(random.uniform(0.1, 0.3))
            logger.info("↩️ Correcting overshoot...")
            
            correction_path = self._generate_path(
                {'x': target_x, 'y': end_y},
                {'x': true_target_x, 'y': end_y},
                steps=random.randint(10, 20)
            )
            for point in correction_path:
                await page.mouse.move(point['x'], point['y'])
                await asyncio.sleep(random.uniform(0.01, 0.02))
                
        # 4. Final adjustments (trembling at the end)
        await asyncio.sleep(random.uniform(0.1, 0.2))
        await page.mouse.move(true_target_x + random.randint(-1, 1), end_y + random.randint(-1, 1))
        
        # 5. Release
        await asyncio.sleep(random.uniform(0.2, 0.5))
        await page.mouse.up()
        logger.info("✅ Slider released")
        
        return True

    async def simple_drag(self, page: Page, start_point: dict, end_point: dict):
        """
        Просте перетягування від точки до точки (для Puzzle/Grid)
        """
        await page.mouse.move(start_point['x'], start_point['y'])
        await page.mouse.down()
        
        path = self._generate_path(start_point, end_point, steps=30)
        for point in path:
            await page.mouse.move(point['x'], point['y'])
            await asyncio.sleep(random.uniform(0.005, 0.02))
            
        await page.mouse.up()


slider_solver = SliderSolver()
