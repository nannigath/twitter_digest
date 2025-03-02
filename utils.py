# utils.py
import os
from datetime import datetime, timedelta
import pandas as pd

def log(message):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def group_by_week(df, end_date):
    log("Grouping data into 7-day intervals with thread grouping...")
    end_date_dt = datetime.strptime(end_date, "%Y-%m-%d")
    if df["date"].dtype == 'O':
        df["date"] = pd.to_datetime(df["date"])
    thread_min_dates = df.groupby("thread_number")["date"].min().reset_index().rename(columns={"date": "thread_min_date"})
    df = df.merge(thread_min_dates, on="thread_number", how="left")
    df["week_group"] = ((end_date_dt - df["thread_min_date"]).dt.days // 7) + 1
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