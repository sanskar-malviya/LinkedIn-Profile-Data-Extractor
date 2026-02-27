from playwright.sync_api import sync_playwright, BrowserContext, Page
import os

class BrowserManager:
    def __init__(self, headless: bool = False, proxy: dict = None, stealth: bool = True):
        self.headless = headless
        self.proxy = proxy
        self.stealth = stealth
        self.playwright = None
        self.browser = None
        self.context = None

    def start(self):
        self.playwright = sync_playwright().start()
        
        args = []
        if self.stealth:
            args.extend([
                '--disable-blink-features=AutomationControlled',
                '--disable-infobars',
                '--start-maximized'
            ])
            
        launch_opts = {
            "headless": self.headless,
            "args": args
        }
        
        if self.proxy:
            launch_opts['proxy'] = {
                "server": f"{self.proxy.get('host')}:{self.proxy.get('port')}",
                "username": self.proxy.get('username'),
                "password": self.proxy.get('password')
            }

        # Use chromium for best compatibility with stealth extensions if needed
        self.browser = self.playwright.chromium.launch(**launch_opts)
        
        viewport = None if '--start-maximized' in args else {'width': 1280, 'height': 720}

        self.context = self.browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="en-US",
            timezone_id="America/New_York",
            viewport=viewport,
            no_viewport=viewport is None
        )
        
        # Add init scripts for stealth
        if self.stealth:
            self.context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                });
            """)

        return self.context

    def close(self):
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()
