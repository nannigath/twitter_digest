# email_sender.py
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib
import logging
import markdown
from datetime import datetime
import re
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging for this module
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] %(levelname)s: %(message)s")

def send_email(summaries, subscriber, start_date, end_date):
    """
    Send an email with a single summary to a subscriber.
    
    Args:
        summaries (dict): Dictionary with one title-summary pair.
        subscriber (str): Email address of the subscriber.
        start_date (str): Start date of the data period (YYYY-MM-DD).
        end_date (str): End date of the data period (YYYY-MM-DD).
    """
    # Load email credentials from environment variables
    EMAIL_SENDER = os.getenv("EMAIL_SENDER")
    EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

    if not EMAIL_SENDER or not EMAIL_PASSWORD:
        raise ValueError("EMAIL_SENDER and EMAIL_PASSWORD must be set in environment variables")

    # Get the current date dynamically for the subject
    current_date = datetime.now().strftime("%B %d, %Y")  # e.g., "March 02, 2025"
    subject = f"Weekly AI Newsletter - {current_date}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = EMAIL_SENDER
    msg["To"] = subscriber

    # Plain text version (single summary)
    title, summary = next(iter(summaries.items()))  # Get the only title-summary pair
    text = f"{title}:\n{summary}\n\nTo unsubscribe, reply with 'unsubscribe'."

    # Convert Markdown to HTML for the summary
    html_content = markdown.markdown(summary, extensions=['extra'])

    # Extract the title dynamically from the first bolded text in the content
    title_match = re.search(r'<strong>(.*?)</strong>', html_content)
    if title_match:
        email_title = title_match.group(1).replace('"', '')  # Remove quotes from the title
        html_content = re.sub(r'<p>.*?<strong>.*?</strong>.*?</p>', '', html_content, count=1)
    else:
        email_title = title  # Use the provided title as fallback

    # Enhanced HTML template with title background
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700&display=swap" rel="stylesheet">
        <style>
            body {{
                font-family: 'Roboto', sans-serif;
                line-height: 1.8;
                color: #333333;
                max-width: 850px;
                margin: 0 auto;
                padding: 30px;
                background: linear-gradient(135deg, #fef9e7 0%, #f5f1e0 100%);
            }}
            h1 {{
                color: #008080;
                background: linear-gradient(to right, #cce5e5 0%, #e6f4ea 100%);
                background-clip: padding-box;
                -webkit-background-clip: padding-box;
                font-size: 32px;
                font-weight: 700;
                text-align: center;
                padding: 10px 20px;
                border-radius: 10px;
                border-bottom: 3px solid #cce5e5;
                margin-bottom: 25px;
                display: inline-block;
                width: auto;
                box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            }}
            h1 span.emoji {{
                background: none;
            }}
            a {{
                color: #0077b6;
                text-decoration: none;
                transition: color 0.3s ease;
            }}
            a:hover {{
                color: #00a3a3;
                text-decoration: underline;
            }}
            .section {{
                background-color: #e6f4ea;
                padding: 20px;
                border-radius: 12px;
                box-shadow: inset 0 0 10px rgba(0, 128, 128, 0.1), 0 4px 10px rgba(0,0,0,0.05);
                margin-bottom: 25px;
            }}
            .emoji {{
                font-size: 24px;
                margin-right: 8px;
                vertical-align: middle;
            }}
            p {{
                margin: 12px 0;
            }}
            .footer {{
                text-align: center;
                font-size: 14px;
                color: #666666;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #dddddd;
            }}
            .highlight {{
                background-color: #d9e8de;
                padding: 3px 10px;
                border-radius: 6px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.05);
            }}
        </style>
    </head>
    <body>
        <div style="text-align: center;">
            <h1><span class="emoji">🔥</span> {email_title}</h1>
        </div>
        <div class="section">
            {html_content}
        </div>
        <div class="footer">
            <p><small>To unsubscribe, reply with 'unsubscribe'.</small></p>
            <p><small>Powered by AITrendSpot</small></p>
        </div>
    </body>
    </html>
    """

    msg.attach(MIMEText(text, "plain"))
    msg.attach(MIMEText(html, "html"))

    # Email sending logic
    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(EMAIL_SENDER, EMAIL_PASSWORD)
            server.send_message(msg)
        logging.info(f"Email sent to {subscriber}")
    except smtplib.SMTPException as e:
        logging.error(f"Failed to send to {subscriber} via Gmail: {e}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error sending to {subscriber}: {e}")
        raise