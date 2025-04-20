import os
from webdriver_manager import WebDriverManager
from twitter_scraper import TwitterScraper
from preprocessor import DataPreprocessor
from summarizer import SummaryGenerator
from utils import log, save_to_csv
from datetime import datetime, timedelta
from dotenv import load_dotenv
from email_sender import send_email
from subscribers import SUBSCRIBERS  # Import SUBSCRIBERS from subscribers.py

# Load environment variables
load_dotenv()

def main():
    # Configuration
    TWITTER_USERNAME = os.getenv("TWITTER_USERNAME")
    TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD")
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    URL = "https://x.com/i/lists/1866834968594317670"
    OUTPUT_DIR = "output"

    required_vars = {
        "TWITTER_USERNAME": TWITTER_USERNAME,
        "TWITTER_PASSWORD": TWITTER_PASSWORD,
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "GOOGLE_API_KEY": GOOGLE_API_KEY
    }
    missing_vars = [key for key, value in required_vars.items() if not value]
    if missing_vars:
        raise ValueError(f"Missing environment variables: {', '.join(missing_vars)}. Please set them in .env file or environment.")

    # Dynamically set date range for the last 7 days
    END_DATE = datetime.now().strftime("%Y-%m-%d")  # Current date
    START_DATE = (datetime.strptime(END_DATE, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")  # 7 days ago
    log(f"Scraping tweets from {START_DATE} to {END_DATE}...")

    # Step 1: Scrape Data
    log("Starting Twitter scraping...")
    driver_manager = WebDriverManager(TWITTER_USERNAME, TWITTER_PASSWORD, headless=False)
    driver_manager.initialize_driver()
    scraper = TwitterScraper(driver_manager)
    df = scraper.fetch_tweets_list(URL, START_DATE, END_DATE)
    driver_manager.close()

    if df.empty:
        log("No data scraped. Exiting.")
        return

    # Step 2: Save Data (No grouping needed)
    csv_file = f"{OUTPUT_DIR}/tweets_last_week.csv"
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        log(f"Created output directory: {OUTPUT_DIR}")
    log(f"Saving last week's data to {csv_file}...")
    df.to_csv(csv_file, index=False)
    log("Data saved successfully.")

    # Step 3: Preprocess and Summarize
    log(f"Preprocessing and summarizing last week's data from {csv_file}...")
    preprocessor = DataPreprocessor(csv_file)
    documents = preprocessor.preprocess_data(include_urls=True)

    summaries = {}

    # Summarize with OpenAI
    # openai_summarizer = SummaryGenerator(model_type="openai", openai_api_key=OPENAI_API_KEY)
    # summary_openai = openai_summarizer.generate_summary(documents, prompt_template="v11")
    # summaries["Last Week (OpenAI)"] = summary_openai

    # Summarize with Gemini
    gemini_summarizer = SummaryGenerator(model_type="gemini", google_api_key=GOOGLE_API_KEY)
    summary_gemini = gemini_summarizer.generate_summary(documents, prompt_template="v12")
    summaries["Last Week (Gemini)"] = summary_gemini

    # Display summaries
    for title, summary in summaries.items():
        log(f"{title} Summary:")
        print(summary)
        print("-" * 50)

    # Step 4: Send Email to Subscribers
    log("Sending emails to subscribers...")
    for subscriber in SUBSCRIBERS:
        try:
            send_email(summaries, subscriber, START_DATE, END_DATE)
            log(f"Successfully sent email to {subscriber}")
        except Exception as e:
            log(f"Failed to send email to {subscriber}: {str(e)}")
    log("Email sending completed.")

if __name__ == "__main__":
    main()