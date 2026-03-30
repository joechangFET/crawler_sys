import random
import asyncio
from typing import Dict, Tuple

from src.utils.jitter import jitter

# Module-level mouse position tracker keyed by page id.
# Playwright does not expose a mouse.position() API, so we track it manually.
_mouse_positions: Dict[int, Tuple[float, float]] = {}


async def human_move_to_element(page, locator, final_offset=(0.5, 0.5)):
    """
    Smoothly move the mouse to a position inside the locator's bounding box.
    final_offset is a (0..1, 0..1) fraction of the element's width/height.
    """
    box = await locator.bounding_box()
    if not box:
        return
    fx = box["x"] + box["width"] * final_offset[0] + random.uniform(-3, 3)
    fy = box["y"] + box["height"] * final_offset[1] + random.uniform(-3, 3)

    steps = random.randint(6, 18)
    mid_x = fx + random.uniform(-40, 40)
    mid_y = fy + random.uniform(-30, -10)

    await page.mouse.move(mid_x, mid_y, steps=max(1, steps // 2))
    await asyncio.sleep(jitter(60) / 1000)

    await page.mouse.move(fx, fy, steps=max(1, steps))
    await asyncio.sleep(jitter(60) / 1000)

    _mouse_positions[id(page)] = (fx, fy)


async def human_click(locator, *, page):
    """Move the mouse to the element, hover briefly, then click."""
    await human_move_to_element(page, locator)
    await locator.hover()
    await asyncio.sleep(jitter(100) / 1000)
    await locator.click(delay=random.randint(30, 120))
    await asyncio.sleep(jitter(150) / 1000)


async def human_move_mouse(page, x, y, steps=20):
    """Move the mouse along a quadratic Bezier curve to (x, y)."""
    sx, sy = _mouse_positions.get(id(page), (0.0, 0.0))
    cx = (sx + x) / 2 + random.randint(-50, 50)
    cy = (sy + y) / 2 + random.randint(-30, 30)

    for i in range(1, steps + 1):
        t = i / steps
        px = (1 - t) ** 2 * sx + 2 * (1 - t) * t * cx + t ** 2 * x
        py = (1 - t) ** 2 * sy + 2 * (1 - t) * t * cy + t ** 2 * y
        await page.mouse.move(px, py)
        await page.wait_for_timeout(jitter(18))

    _mouse_positions[id(page)] = (x, y)


async def human_scroll(page, total=2000):
    scrolled = 0
    while scrolled < total:
        delta = random.randint(120, 480)
        await page.mouse.wheel(0, delta)
        scrolled += delta
        await page.wait_for_timeout(jitter(400))
        if random.random() < 0.12:
            await page.mouse.wheel(0, -random.randint(60, 200))
            await page.wait_for_timeout(jitter(300))


async def human_type(locator, text: str):
    for ch in text:
        await locator.type(ch, delay=jitter(80))
        if random.random() < 0.02:
            await locator.type(random.choice("asdfjkl;"), delay=jitter(70))
            await locator.press("Backspace")


async def wait_page_ready(page):
    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_load_state("networkidle")
    await page.wait_for_timeout(jitter(600))
