
import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from selenium import webdriver
from urllib.parse import urlparse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException

def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


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
            # Enter username
            username_field = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located((By.NAME, "text"))
            )
            username_field.send_keys(self.username)
            username_field.send_keys("\n")

            # Enter password
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
        self.close()  # Close the existing session if it's active
        self.initialize_driver()  # Reinitialize the driver

    def close(self):
        if self.driver:
            self.driver.quit()


class TwitterScraper:
    """
    Handles tweet extraction, processing, and analysis.
    """
    
    def __init__(self, driver_manager):
        self.driver_manager = driver_manager
        self.driver = self.driver_manager.driver
    
    def _initialize_driver(self):
        """
        Reinitialize the driver if it crashes.
        """
        log("Reinitializing WebDriver...")
        self.driver_manager.restart_driver()
        self.driver = self.driver_manager.driver
    
    def _get_first_tweet(self, timeout=10, max_retries=5, retry_delay=2):
        """
        Retrieve the first tweet element from the page.
        """
        retries = 0
        while retries < max_retries:
            try:
                #log("Searching for first tweet...")
                WebDriverWait(self.driver, timeout).until(
                    lambda d: d.find_elements(By.XPATH, "//article[@data-testid='tweet']")
                )
                #log("Tweet found!")
                return self.driver.find_element(By.XPATH, "//article[@data-testid='tweet']")
            except (TimeoutException, NoSuchElementException, StaleElementReferenceException):
                log(f"Retrying tweet search ({retries + 1}/{max_retries})...")
                retries += 1
                time.sleep(retry_delay)
        log("No tweet found after retries.")
        return None
    
    def resume_from_last_processed(self, last_processed_tweet_url, url):
        """
        After restarting the driver, load the URL and delete tweets until
        the last processed tweet (identified by its URL) is removed,
        so that processing resumes with tweets that haven't been seen.
        """
        log(f"Resuming from last processed tweet: {last_processed_tweet_url}")
        self.driver.get(url)
        # Wait for tweets to load
        time.sleep(5)
        try:
            while True:
                tweet_element = self._get_first_tweet()
                if not tweet_element:
                    break
                tweet_url = self.get_tweet_url(tweet_element)
                if tweet_url == last_processed_tweet_url:
                    # Delete the already-processed tweet and break out.
                    self._delete_first_tweet()
                    log("Found and deleted last processed tweet; resuming processing after this tweet.")
                    break
                else:
                    # Delete tweets that were already processed
                    self._delete_first_tweet()
        except Exception as e:
            log(f"Error resuming from last processed tweet: {str(e)}")
    
    def fetch_tweets_list(self, url, start_date, end_date, time_threshold_minutes=2):
        log(f"Fetching tweets from {url}...")
        self.driver.get(url)
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        tweets = []
        count = 0
        refresh_needed = False
        
        while True:
            try:
                if self.driver is None:
                    log("WebDriver session lost. Restarting driver...")
                    self.driver_manager.restart_driver()
                    self.driver = self.driver_manager.driver
                
                tweet_element = self._get_first_tweet()
                if not tweet_element:
                    continue
                
                tweet_data = self._process_tweet(tweet_element)
                if not tweet_data:
                    continue
                
                log(f"Processing tweet from {tweet_data['author_name']}, date: {tweet_data['date']}")
                tweet_date = datetime.strptime(tweet_data["date"], "%Y-%m-%d")
                
                if tweet_date < start_date_obj and not tweet_data['is_reposted']:
                    log("Tweet is older than start date. Checking next tweets...")
                    
                    old_tweets = [tweet_data]
                    for _ in range(2):
                        self._clear_processed_tweet(tweet_element)
                        next_tweet_element = self._get_first_tweet()
                        if not next_tweet_element:
                            continue
                        next_tweet_data = self._process_tweet(next_tweet_element)
                        if not next_tweet_data:
                            continue
                        next_tweet_date = datetime.strptime(next_tweet_data["date"], "%Y-%m-%d")
                        old_tweets.append(next_tweet_data)
                        
                        if next_tweet_date >= start_date_obj:
                            log("Found a valid tweet within the range. Continuing...")
                            tweets.extend(old_tweets)
                            break
                    else:
                        log("No valid tweets found within range. Stopping.")
                        break
                    
                    continue
                elif tweet_date > end_date_obj:
                    log("Tweet is newer than end date. Deleting and continuing...")
                    self._clear_processed_tweet(tweet_element)
                    continue
                
                tweets.append(tweet_data)
                self._clear_processed_tweet(tweet_element)
                count += 1
                
                # if count % 50 == 0:
                #     refresh_needed = True
                #     log("Refreshing page after 50 tweets...")
                #     self.driver.refresh()
                #     time.sleep(5)
                
                if count % 100 == 0:
                    log("Triggering Chrome garbage collection...")
                    self.driver.execute_script("window.gc();")
            
            except Exception as e:
                log(f"Error processing tweet: {str(e)}")
                time.sleep(5)
        
        return self._process_dataframe(tweets, time_threshold_minutes)
    
    def _clear_processed_tweet(self, tweet_element):
        try:
            self.driver.execute_script("arguments[0].remove();", tweet_element)
        except Exception as e:
            log(f"Error clearing tweet element: {str(e)}")


    
    def _delete_first_tweet(self):
        """
        Remove the first tweet from the page.
        """
        try:
            #log("Deleting first tweet...")
            tweet_element = self.driver.find_element(By.XPATH, "//article[@data-testid='tweet'][1]")
            #log(f"Tweet deleted: {tweet_element.text[:50]}...")
            self.driver.execute_script("arguments[0].remove();", tweet_element)
        except NoSuchElementException:
            log("No tweet to delete.")
    
    def _process_dataframe(self, tweets, time_threshold_minutes):
        """
        Process the extracted tweets into a structured DataFrame with thread numbers.
        """
        log("Processing tweets into DataFrame...")
        df = pd.DataFrame(tweets)
        
        if df.empty:
            log("No tweets found.")
            return df
        
        df["datetime"] = pd.to_datetime(df["date"] + " " + df["time"])
        df.sort_values(by=["author_name", "datetime"], inplace=True)
        
        thread_numbers = []
        thread_count = 0
        
        for author, group in df.groupby("author_name"):
            last_datetime = None
            for idx, row in group.iterrows():
                if last_datetime is None or (row["datetime"] - last_datetime).total_seconds() > time_threshold_minutes * 60:
                    thread_count += 1
                thread_numbers.append(thread_count)
                last_datetime = row["datetime"]
        
        df["thread_number"] = thread_numbers
        df.drop(columns=["datetime"], inplace=True)
        log("DataFrame processing complete.")
        return df
    
    def _process_tweet(self, tweet_element):
        """
        Process a single tweet element and extract relevant information.
        """
        try:
            #log("Extracting tweet details...")
            author_details = self.get_element_text(tweet_element, ".//div[@data-testid='User-Name']")
            parts = author_details.split("\n")
            author_name, author_handle = parts[0], parts[1] if len(parts) > 1 else ""
            
            tweet_datetime_str = self.get_element_attribute(tweet_element, "time", "datetime")
            tweet_datetime = datetime.strptime(tweet_datetime_str, "%Y-%m-%dT%H:%M:%S.000Z")
            
            return {
                "text": self.get_element_text(tweet_element, ".//div[@data-testid='tweetText']"),
                "author_name": author_name,
                "author_handle": author_handle,
                "date": tweet_datetime.strftime('%Y-%m-%d'),
                "time": tweet_datetime.strftime('%H:%M:%S'),
                "lang": self.get_element_attribute(tweet_element, "div[data-testid='tweetText']", "lang"),
                "tweet_url": self.get_tweet_url(tweet_element),
                "mentioned_urls": self.get_mentioned_urls(tweet_element),
                "is_reposted": self.is_retweet(tweet_element),
                "media_type": self.get_media_type(tweet_element),
                "image_urls": self.get_images_urls(tweet_element)
            }
        except Exception as e:
            log(f"Error processing tweet: {str(e)}")
            return None
    
    def get_element_text(self, parent, xpath):
        try:
            return parent.find_element(By.XPATH, xpath).text
        except NoSuchElementException:
            return ""
    
    def get_element_attribute(self, parent, selector, attribute):
        try:
            return parent.find_element(By.CSS_SELECTOR, selector).get_attribute(attribute)
        except NoSuchElementException:
            return ""
    
    def get_tweet_url(self, tweet_element):
        try:
            link_element = tweet_element.find_element(By.XPATH, ".//a[contains(@href, '/status/')]")
            return link_element.get_attribute("href")
        except NoSuchElementException:
            return ""
    
    def get_mentioned_urls(self, tweet_element):
        try:
            link_elements = tweet_element.find_elements(By.XPATH, ".//a[contains(@href, 'http')]")
            return [elem.get_attribute("href") for elem in link_elements]
        except NoSuchElementException:
            return []
    
    def is_retweet(self, tweet_element):
        try:
            return bool('reposted' in tweet_element.find_element(By.XPATH,'.//span').text)
        except NoSuchElementException:
            return False
    
    def get_media_type(self, tweet_element):
        if tweet_element.find_elements(By.CSS_SELECTOR, "div[data-testid='videoPlayer']"):
            return "Video"
        if tweet_element.find_elements(By.CSS_SELECTOR, "div[data-testid='tweetPhoto']"):
            return "Image"
        return "No media"
    
    def get_images_urls(self, tweet_element):
        image_elements = tweet_element.find_elements(By.XPATH, ".//div[@data-testid='tweetPhoto']//img")
        return [img.get_attribute("src") for img in image_elements]

    def download_images(self, df, output_dir='downloaded_images', timeout=10, chunk_size=8192, delay=1):
        """
        Download images from tweets and save them in a given folder
        """
   
        os.makedirs(output_dir, exist_ok=True)
        
        for _, row in df.iterrows():
            if not row.get('image_urls'):
                continue  # Skip rows without image URLs
            
            # Parse tweet details for naming files
            url_parts = urlparse(row['tweet_url'])
            twitter_name = url_parts.path.split('/')[1]
            tweet_id = url_parts.path.split('/')[-1]
            
            for i, image_url in enumerate(row['image_urls'], start=1):
                image_id = f"{twitter_name}__{tweet_id}_{i}"
                image_path = os.path.join(output_dir, f"{image_id}.jpg")
                
                # Skip download if the file already exists
                if os.path.exists(image_path):
                    print(f"Image already exists: {image_id}")
                    continue
                
                try:
                    # Download image
                    response = requests.get(image_url, stream=True, timeout=timeout)
                    response.raise_for_status()
                    
                    with open(image_path, 'wb') as file:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            file.write(chunk)
                    
                    print(f"Successfully downloaded image: {image_id}")
                    
                    # Delay to prevent rate-limiting
                    time.sleep(delay)
                
                except requests.exceptions.RequestException as e:
                    print(f"Error downloading image: {image_id}")
                    print(f"Error message: {str(e)}")
    
        print("Image download completed.")


def group_by_week(df, end_date):
    log("Grouping data into 7-day intervals with thread grouping...")
    end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
    
    # Ensure the 'date' column is in datetime format
    if df["date"].dtype == 'O':  # if it's an object (likely string)
        df["date"] = pd.to_datetime(df["date"])
    
    # Compute the earliest tweet date for each thread (using the existing 'date' column)
    thread_min_dates = df.groupby("thread_number")["date"].min().reset_index().rename(columns={"date": "thread_min_date"})
    
    # Merge the thread's minimum date back into the DataFrame
    df = df.merge(thread_min_dates, on="thread_number", how="left")
    
    # Assign a week group based on the thread's earliest tweet date
    df["week_group"] = ((end_date_dt - df["thread_min_date"]).dt.days // 7) + 1
    
    # Sort by thread and date for consistency
    df.sort_values(by=["thread_number", "date"], inplace=True)
    return df

def save_to_csv(df, output_dir="output", base_filename="tweets_week"): 
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    for week, group in df.groupby("week_group"):
        filename = os.path.join(output_dir, f"{base_filename}_{week}.csv")
        log(f"Saving week {week} data to {filename}...")
        group.drop(columns=["week_group"], inplace=True)
        group.to_csv(filename, index=False)
        log(f"Week {week} file saved successfully.")

def main():

    USERNAME = "aitrendspot"
    PASSWORD = "Spotl!ght08"
    
    driver_manager = WebDriverManager(USERNAME, PASSWORD, headless=False)
    driver_manager.initialize_driver()
    auth_token = driver_manager.get_auth_token()
    
    url = "https://x.com/i/lists/1866834968594317670"
    end_date = "2025-02-20"
    start_date = (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=8)).strftime("%Y-%m-%d")
    
    scraper = TwitterScraper(driver_manager)
    df = scraper.fetch_tweets_list(url, start_date, end_date)
    
    if not df.empty:
        df = group_by_week(df, end_date)
        save_to_csv(df)
    else:
        log("No data to save.")
    
if __name__ == "__main__":
    main()