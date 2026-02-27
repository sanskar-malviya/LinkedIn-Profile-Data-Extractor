import os
import json
import logging
from playwright.sync_api import Page, expect
from scraper.utils import random_delay, simulate_typing, human_like_mouse_movement

logger = logging.getLogger(__name__)

class AuthManager:
    def __init__(self, context, credentials: dict, session_file: str = "session.json"):
        self.context = context
        self.credentials = credentials
        self.session_file = session_file

    def login(self) -> Page:
        """Handles the login process, either via cookies or starting a fresh session."""
        page = self.context.new_page()
        
        if self._load_session():
            logger.info("Session loaded from file. Validating...")
            if self._validate_session(page):
                return page
            else:
                logger.info("Session invalid. Proceeding with fresh login.")
                self.context.clear_cookies()
        else:
            logger.info("No session file found. Proceeding with fresh login.")

        return self._do_fresh_login(page)

    def _load_session(self) -> bool:
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    cookies = json.load(f)
                    self.context.add_cookies(cookies)
                return True
            except Exception as e:
                logger.error(f"Error loading session file: {e}")
        return False

    def _save_session(self):
        cookies = self.context.cookies()
        with open(self.session_file, 'w') as f:
            json.dump(cookies, f)
        logger.info("Session saved securely.")

    def _validate_session(self, page: Page) -> bool:
        """Navigates to the feed to check if the session is alive."""
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        random_delay(2, 4)
        if "feed" in page.url or "mynetwork" in page.url:
            return True
        return False

    def _do_fresh_login(self, page: Page) -> Page:
        logger.info("Navigating to login page...")
        page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded")
        
        random_delay(1, 3)
        page.wait_for_selector("#username", state="visible")
        
        # Simulate human interaction
        page.mouse.move(100, 100)
        random_delay(0.5, 1.5)
        
        simulate_typing(page, "#username", self.credentials['username'])
        random_delay(1, 2)
        
        simulate_typing(page, "#password", self.credentials['password'])
        random_delay(0.5, 1.5)
        
        page.click("button[type='submit']")
        
        self._handle_post_login_checks(page)
        
        self._save_session()
        return page
        
    def _handle_post_login_checks(self, page: Page):
        """Wait for either a successful login or a challenge."""
        logger.info("Waiting for post-login redirection...")
        page.wait_for_timeout(5000) # Give it 5 seconds to load whatever comes next
        
        current_url = page.url
        
        if "feed" in current_url:
            logger.info("Login successful. Feed page reached.")
            return
            
        if "checkpoint" in current_url or "challenge" in current_url:
            logger.warning("Checkpoint or 2FA challenge detected!")
            self._handle_challenge(page)
            return

        # If it's still on login page with an error
        if "login" in current_url:
            error_el = page.query_selector("#error-for-password")
            if error_el:
                raise Exception(f"Login failed: {error_el.inner_text()}")
            raise Exception("Login failed. Checkpoint/error not explicitly detected but not on feed.")
            
        logger.info("Landed on unknown page, assuming success for now but monitoring.")

    def _handle_challenge(self, page: Page):
        """Pause execution to allow the user to solve the challenge manually."""
        logger.warning("\n==================================")
        logger.warning("MANUAL INTERVENTION REQUIRED")
        logger.warning("Please solve the CAPTCHA or 2FA in the opened browser window.")
        logger.warning("Press ENTER here in the console once you are logged in and see the Feed page.")
        logger.warning("==================================\n")
        
        # Pause execution. In headless mode, this will hang. We need to rely on the user seeing the logs.
        # But this script runs in the backend. 
        # A more advanced workflow would send a notification or use a specific wait logic.
        input("Press enter after solving the challenge...")
        
        # Re-verify
        if "feed" not in page.url:
             page.goto("https://www.linkedin.com/feed/")
             page.wait_for_selector(".feed-shared-update-v2", timeout=10000)
             
        logger.info("Challenge solved successfully.")
