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

def scroll_to_bottom(page: Page, max_scrolls: int = 30):
    """Scroll down the page slowly and incrementally to trigger lazy loaded elements.

    LinkedIn virtualizes its DOM and uses IntersectionObserver for lazy loading.
    We must scroll slowly enough for each section to enter the viewport and render.
    """
    last_height = page.evaluate("document.documentElement.scrollHeight")
    scroll_count = 0
    stale_count = 0

    while scroll_count < max_scrolls and stale_count < 4:
        # Scroll by half a viewport (~400px) to ensure overlap
        scroll_amount = random.randint(300, 500)
        page.evaluate(f"window.scrollBy(0, {scroll_amount})")
        # Wait longer for LinkedIn's lazy loading to trigger
        random_delay(1.5, 2.5)

        new_height = page.evaluate("document.documentElement.scrollHeight")
        if new_height == last_height:
            stale_count += 1
            # Wait extra on stale to give pending loads more time
            random_delay(1.0, 1.5)
        else:
            stale_count = 0
        last_height = new_height
        scroll_count += 1

    # Final scroll to absolute bottom and wait
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    random_delay(2.0, 3.0)

    # Scroll back up slowly to re-trigger any sections that got virtualized away
    current_pos = page.evaluate("window.scrollY")
    while current_pos > 0:
        step = random.randint(800, 1200)
        current_pos = max(0, current_pos - step)
        page.evaluate(f"window.scrollTo(0, {current_pos})")
        random_delay(0.8, 1.5)

    # One final slow scroll down to ensure everything is loaded
    total_height = page.evaluate("document.documentElement.scrollHeight")
    position = 0
    while position < total_height:
        position += random.randint(400, 600)
        page.evaluate(f"window.scrollTo(0, {min(position, total_height)})")
        random_delay(1.0, 1.5)

    random_delay(1.0, 2.0)

def scroll_to_element(page: Page, locator):
    """Scroll a Playwright locator into view."""
    try:
        locator.scroll_into_view_if_needed(timeout=5000)
    except Exception:
        pass
    random_delay(0.5, 1.0)
