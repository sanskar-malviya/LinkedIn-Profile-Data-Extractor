import random
import time
from playwright.sync_api import Page, Mouse

def random_delay(min_seconds: float = 1.0, max_seconds: float = 3.0):
    """Introduce a random human-like delay."""
    time.sleep(random.uniform(min_seconds, max_seconds))

def simulate_typing(page: Page, selector: str, text: str, delay: int = 100):
    """Simulate human typing by adding random delays between key presses."""
    page.click(selector)
    page.type(selector, text, delay=delay)
    random_delay(0.5, 1.5)

async def human_like_mouse_movement(page: Page):
    """Moves the mouse randomly across the screen."""
    # Assuming standard viewport of 1280x720 if not set
    for _ in range(3):
        x = random.randint(100, 1000)
        y = random.randint(100, 600)
        page.mouse.move(x, y, steps=10)
        random_delay(0.2, 0.8)

def scroll_to_bottom(page: Page):
    """Scroll down the page to trigger lazy loaded elements."""
    last_height = page.evaluate("document.body.scrollHeight")
    while True:
        page.keyboard.press("End")
        random_delay(1.5, 3.0)
        
        # Adding a little jiggle
        page.mouse.wheel(delta_x=0, delta_y=-100)
        random_delay(0.5, 1.0)
        page.mouse.wheel(delta_x=0, delta_y=300)

        new_height = page.evaluate("document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height
