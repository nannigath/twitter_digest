from selenium import webdriver
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By

class WebDriverManager:
    """
    Manages WebDriver initialization, configuration, and browser sessions.
    """
    def __init__(self, auth_token=None, headless=True):
       
        self.driver = None
        self.auth_token = auth_token
        self.headless = headless
    
    def initialize_driver(self):
        """
        Initialize and configure the Selenium WebDriver.
        """
        options = webdriver.ChromeOptions()
        options.add_argument("--verbose")
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920, 1200")
        options.add_argument('--disable-dev-shm-usage')
        options.headless = self.headless
        
        self.driver = webdriver.Chrome(options=options)
        self.driver.get("https://x.com")
        
        if self.auth_token:
            self._set_auth_token()
        
        return self.driver
    
    def _set_auth_token(self):
        """
        Set authentication token as a cookie.
        """
        if not self.auth_token:
            raise ValueError("Access token is missing. Please configure it properly.")
        
        expiration = (datetime.now() + timedelta(days=14)).strftime("%Y-%m-%d")
        cookie_script = f"document.cookie = 'auth_token={self.auth_token}; expires={expiration}; path=/';"
        self.driver.execute_script(cookie_script)
    
    def get_current_tweet(self):
        """
        Retrieve the currently visible tweet on the page.
        """
        try:
            current_tweet_element = self.driver.find_element(By.XPATH, "//article[@role='article']")
            return current_tweet_element if current_tweet_element else None
        except Exception as e:
            print(f"Error while fetching the current tweet: {str(e)}")
            return None
    
    def close(self):
        """
        Close the WebDriver and end the session.
        """
        if self.driver:
            self.driver.quit()