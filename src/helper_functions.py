import logging
from tqdm import tqdm
import time
import requests
import pandas as pd

def check_request(response, url, params=None):
    # Enter delay loop if error code 429
    while response.status_code == 429:  # Error code 429 is rate limit of api calls reached
        logging.warning("Rate Limit Exceeded, trying again in 5 seconds...")
        for _ in tqdm(range(5)):  # tqdm to keep loading bar
            time.sleep(1)
        if params is None:
            response = requests.get(url)  # try again
        else:
            response = requests.get(url, params=params)

    # Other error code
    if response.status_code != 200:
        message = f"Unexpected response from OpenF1 API: {response.status_code}"
        logging.error(message)
        raise ValueError(message)

    # Extract data and check
    data = response.json()
    if not data:
        message = "No session data found for the given session key."
        logging.error(message)
        raise ValueError(message)

    return data

def get_f1_weekends(year):
    params = {"year": year}
    url = "https://api.openf1.org/v1/meetings"
    response = requests.get(url, params=params)
    data = check_request(response, url, params)
    data_df = pd.DataFrame(data)
    data_tuples = list(zip(data_df['meeting_official_name'], data_df['meeting_key']))
    unique_tuples = pd.unique(data_tuples)

    return unique_tuples

def get_sessions_in_weekend(meeting_key):
    params = {"meeting_key": meeting_key}
    url = "https://api.openf1.org/v1/sessions"
    response = requests.get(url, params=params)
    data = check_request(response, url, params)
    data_df = pd.DataFrame(data)
    data_tuples = list(zip(data_df['session_name'], data_df['session_key']))
    unique_tuples = pd.unique(data_tuples)

    return unique_tuples

def format_lap_time(t):
    minutes = int(t // 60)
    seconds = int(t % 60)
    milliseconds = int((t - int(t)) * 1000)
    return f"{minutes}:{seconds:02d}.{milliseconds:03d}"