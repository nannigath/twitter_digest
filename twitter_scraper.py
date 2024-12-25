import os
import time
import requests
import pandas as pd
from urllib.parse import urlparse
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait

class TwitterScraper:
    """
    Handles tweet extraction, processing, and analysis.
    """
    
    def __init__(self, driver_manager=None):
        self.driver_manager = driver_manager or WebDriverManager()
        self.driver = self.driver_manager.driver
    
    def _get_first_tweet(self, timeout=10, max_retries=5, retry_delay=2):
        """
        Retrieve the first tweet element from the page.
        """
        retries = 0
        while retries < max_retries:
            try:
                WebDriverWait(self.driver, timeout).until(
                    lambda d: d.find_elements(By.XPATH, "//article[@data-testid='tweet']")
                )
                return self.driver.find_element(By.XPATH, "//article[@data-testid='tweet']")
            except TimeoutException:
                retries += 1
                time.sleep(retry_delay)
        
        return None
    
    def fetch_tweets_list(self, url, start_date, end_date, time_threshold_minutes=2):
        """
        Fetch tweets from a given tweet list URL within a specified date range and assign thread numbers.
        """
        if not self.driver:
            self.driver_manager.initialize_driver()
        
        self.driver.get(url)
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
        count = 0
       
        tweets = []
        while True:
           
            tweet_element = self._get_first_tweet()
            tweet_data = self._process_tweet(tweet_element)
            if not tweet_data:
                continue
            
            tweet_date = datetime.strptime(tweet_data["date"], "%Y-%m-%d")
            tweets.append(tweet_data)
            if tweet_date < start_date_obj:
                if not tweet_data['is_reposted']:
                    break
            elif tweet_date > end_date_obj:
                count+=1
                self._delete_first_tweet()
                
                continue
            
            self._delete_first_tweet()
        
        df = pd.DataFrame(tweets)
        
        if not df.empty:
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
        
        return df
    
    def _delete_first_tweet(self):
        """
        Remove the first tweet from the page 
        """
        try:
            tweet_element = self.driver.find_element(By.XPATH, "//article[@data-testid='tweet'][1]")
            self.driver.execute_script("arguments[0].remove();", tweet_element)
        except NoSuchElementException:
            print("No tweet to delete.")
    
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
    
    def _process_tweet(self, tweet_element):
        """
        Process a single tweet element and extract relevant information.
        """
        try:
            author_details = self.get_element_text(tweet_element, ".//div[@data-testid='User-Name']")
            parts = author_details.split("\n")
            author_name, author_handle = parts[0], parts[1] if len(parts) > 1 else ""
            
            tweet_datetime_str = self.get_element_attribute(tweet_element, "time", "datetime")
            tweet_datetime = datetime.strptime(tweet_datetime_str, "%Y-%m-%dT%H:%M:%S.000Z")
            tweet_date = tweet_datetime.date()
            tweet_time = tweet_datetime.time()
            
            tweet_data = {
                "text": self.get_element_text(tweet_element, ".//div[@data-testid='tweetText']"),
                "author_name": author_name,
                "author_handle": author_handle,
                "date": tweet_date.strftime('%Y-%m-%d'),
                "time": tweet_time.strftime('%H:%M:%S'),
                "lang": self.get_element_attribute(tweet_element, "div[data-testid='tweetText']", "lang"),
                "tweet_url": self.get_tweet_url(tweet_element),
                "mentioned_urls": self.get_mentioned_urls(tweet_element),
                "is_reposted": self.is_retweet(tweet_element),
                "media_type": self.get_media_type(tweet_element),
                "image_urls": self.get_images_urls(tweet_element)
            }
            return tweet_data
        except Exception as e:
            print(f"Error processing tweet: {str(e)}")
            return None

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