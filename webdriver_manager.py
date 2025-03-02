# webdriver_manager.py
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time

class WebDriverManager:
    def __init__(self, username, password, headless=True):
        self.username = username
        self.password = password
        self.headless = headless
        self.driver = None

    def initialize_driver(self):
        options = webdriver.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument('--disable-gpu')
        options.add_argument("--window-size=1920, 1200")
        options.add_argument('--disable-dev-shm-usage')
        if self.headless:
            options.add_argument("--headless")

        self.driver = webdriver.Chrome(options=options)
        self.driver.get("https://twitter.com/login")
        self._login()
        return self.driver

    def _login(self):
        try:
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "text"))
            )
            username_field.send_keys(self.username)
            username_field.send_keys("\n")

            password_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "password"))
            )
            password_field.send_keys(self.password)
            password_field.send_keys("\n")

            time.sleep(5)  # Wait for login
        except Exception as e:
            print(f"Login failed: {str(e)}")

    def get_auth_token(self):
        cookies = self.driver.get_cookies()
        for cookie in cookies:
            if cookie["name"] == "auth_token":
                return cookie["value"]
        return None

    def restart_driver(self):
        print("Restarting WebDriver...")
        self.close()
        self.initialize_driver()

    def close(self):
        if self.driver:
            self.driver.quit()