# preprocessor.py
import re
import time
import requests
import pandas as pd
from langchain_community.document_loaders.telegram import text_to_docs

class DataPreprocessor:
    def __init__(self, file_path):
        """Initialize with the path to the CSV file."""
        self.file_path = file_path
        self.df = None
        self.combined_tweets = None

    def resolve_shortened_url(self, short_url):
        """Resolve a shortened URL to its full form."""
        try:
            response = requests.head(short_url, allow_redirects=True)
            time.sleep(0.5)  # Avoid rate limiting
            return response.url
        except requests.RequestException as e:
            print(f"Error resolving URL {short_url}: {e}")
            return short_url

    def resolve_urls_in_text(self, text):
        """Extract and resolve URLs in a text string."""
        url_pattern = r'https?://\S+|www\.\S+'
        urls = re.findall(url_pattern, text)
        for url in urls:
            resolved_url = self.resolve_shortened_url(url)
            text = text.replace(url, resolved_url)
        return text

    def preprocess_data(self, include_urls=True):
        """Preprocess the CSV data and combine tweets by thread."""
        # Load data
        self.df = pd.read_csv(self.file_path)
        self.df['text'] = self.df['text'].fillna('').astype(str)

        if include_urls:
            # Resolve URLs in text
            self.df['text'] = self.df['text'].apply(self.resolve_urls_in_text)
            # Handle mentioned_urls column
            self.df['mentioned_urls'] = self.df['mentioned_urls'].apply(
                lambda x: [self.resolve_shortened_url(url) for url in eval(x)] if pd.notna(x) else []
            )
            # Combine text and URLs
            self.df['text_with_urls'] = self.df.apply(
                lambda row: row['text'] + ' ' + ' '.join(row['mentioned_urls']), axis=1
            )
            # Group by thread_number
            df_new = self.df.groupby("thread_number")["text_with_urls"].apply(" ".join).reset_index()
            df_new = df_new.rename(columns={"text_with_urls": "combined_tweet"})
        else:
            # Group by thread_number without URLs
            df_new = self.df.groupby("thread_number")["text"].apply(" ".join).reset_index()
            df_new = df_new.rename(columns={"text": "combined_tweet"})

        # Filter tweets longer than 20 characters
        combined_tweets = df_new['combined_tweet'].to_list()
        combined_tweets = [i for i in combined_tweets if len(i) > 20]
        self.combined_tweets = text_to_docs(str(combined_tweets))

        return self.combined_tweets