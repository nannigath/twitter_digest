import os
import time
import pandas as pd
from datetime import datetime
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, StaleElementReferenceException
from utils import log
from urllib.parse import urlparse
import requests

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
                WebDriverWait(self.driver, timeout).until(
                    lambda d: d.find_elements(By.XPATH, "//article[@data-testid='tweet']")
                )
                return self.driver.find_element(By.XPATH, "//article[@data-testid='tweet']")
            except (TimeoutException, NoSuchElementException, StaleElementReferenceException):
                log(f"Retrying tweet search ({retries + 1}/{max_retries})...")
                retries += 1
                time.sleep(retry_delay)
        log("No tweet found after retries.")
        return None
    
    def _get_tweet_xpath(self):
        """
        Return the XPath for the first tweet element.
        """
        return "//article[@data-testid='tweet']"
    
    def _safe_clear_processed_tweet(self, tweet_element):
        """
        Safely clear a processed tweet, handling stale elements.
        """
        try:
            WebDriverWait(self.driver, 5).until(EC.element_to_be_clickable(tweet_element))
            self._clear_processed_tweet(tweet_element)
        except (StaleElementReferenceException, TimeoutException):
            log("Failed to clear tweet due to stale element or timeout. Skipping...")
            pass
    
    def resume_from_last_processed(self, last_processed_tweet_url, url):
        """
        After restarting the driver, load the URL and delete tweets until
        the last processed tweet (identified by its URL) is removed,
        so that processing resumes with tweets that haven't been seen.
        """
        log(f"Resuming from last processed tweet: {last_processed_tweet_url}")
        self.driver.get(url)
        time.sleep(5)
        try:
            while True:
                tweet_element = self._get_first_tweet()
                if not tweet_element:
                    break
                tweet_url = self.get_tweet_url(tweet_element)
                if tweet_url == last_processed_tweet_url:
                    self._delete_first_tweet()
                    log("Found and deleted last processed tweet; resuming processing after this tweet.")
                    break
                else:
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
        
        while True:
            try:
                if self.driver is None:
                    log("WebDriver session lost. Restarting driver...")
                    self.driver_manager.restart_driver()
                    self.driver = self.driver_manager.driver
                
                tweet_element = WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, self._get_tweet_xpath()))
                )
                if not tweet_element:
                    log("No tweet element found. Continuing...")
                    continue
                
                tweet_data = self._process_tweet(tweet_element)
                if not tweet_data:
                    log("Failed to process tweet data. Continuing...")
                    self._safe_clear_processed_tweet(tweet_element)
                    continue
                
                log(f"Processing tweet from {tweet_data['author_name']}, date: {tweet_data['date']}")
                tweet_date = datetime.strptime(tweet_data["date"], "%Y-%m-%d")
                
                if tweet_date < start_date_obj and not tweet_data['is_reposted']:
                    log("Tweet is older than start date. Checking next tweets...")
                    old_tweets = [tweet_data]
                    for _ in range(2):
                        self._safe_clear_processed_tweet(tweet_element)
                        try:
                            next_tweet_element = WebDriverWait(self.driver, 10).until(
                                EC.presence_of_element_located((By.XPATH, self._get_tweet_xpath()))
                            )
                        except TimeoutException:
                            log("No next tweet found. Stopping.")
                            break
                        
                        next_tweet_data = self._process_tweet(next_tweet_element)
                        if not next_tweet_data:
                            log("Failed to process next tweet. Continuing...")
                            continue
                        
                        next_tweet_date = datetime.strptime(next_tweet_data["date"], "%Y-%m-%d")
                        log(f"Next tweet date: {next_tweet_date}")
                        old_tweets.append(next_tweet_data)
                        
                        if next_tweet_date >= start_date_obj:
                            log("Found a valid tweet within the range. Continuing...")
                            tweets.extend(old_tweets)
                            break
                        tweet_element = next_tweet_element
                    else:
                        log("No valid tweets found within range. Stopping.")
                        break
                    continue
                elif tweet_date > end_date_obj:
                    log("Tweet is newer than end date. Deleting and continuing...")
                    self._safe_clear_processed_tweet(tweet_element)
                    continue
                
                tweets.append(tweet_data)
                self._safe_clear_processed_tweet(tweet_element)
                count += 1
                
                if count % 100 == 0:
                    log("Triggering Chrome garbage collection...")
                    self.driver.execute_script("window.gc();")
            
            except StaleElementReferenceException:
                log("Stale element detected. Re-fetching tweet element...")
                continue
            except Exception as e:
                log(f"Error processing tweet: {str(e)}")
                time.sleep(5)
                continue
        
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
            tweet_element = self.driver.find_element(By.XPATH, "//article[@data-testid='tweet'][1]")
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
                continue
            
            url_parts = urlparse(row['tweet_url'])
            twitter_name = url_parts.path.split('/')[1]
            tweet_id = url_parts.path.split('/')[-1]
            
            for i, image_url in enumerate(row['image_urls'], start=1):
                image_id = f"{twitter_name}__{tweet_id}_{i}"
                image_path = os.path.join(output_dir, f"{image_id}.jpg")
                
                if os.path.exists(image_path):
                    print(f"Image already exists: {image_id}")
                    continue
                
                try:
                    response = requests.get(image_url, stream=True, timeout=timeout)
                    response.raise_for_status()
                    
                    with open(image_path, 'wb') as file:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            file.write(chunk)
                    
                    print(f"Successfully downloaded image: {image_id}")
                    time.sleep(delay)
                
                except requests.exceptions.RequestException as e:
                    print(f"Error downloading image: {image_id}")
                    print(f"Error message: {str(e)}")
    
        print("Image download completed.")