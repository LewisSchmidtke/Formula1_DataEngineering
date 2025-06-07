import time
from datetime import timedelta
import requests
import pandas as pd
import numpy as np

from typing import List, Tuple, Union

from tqdm import tqdm
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import seaborn as sns


COMPOUND_COLORS = {
    "SOFT": "#FF0000",        # Red
    "MEDIUM": "#FFD800",      # Yellow
    "HARD": "#808080",        # Dark grey
    "INTERMEDIATE": "#00A550",# Green
    "WET": "#0072C6",         # Blue
}


lap_url = "https://api.openf1.org/v1/laps"
car_url = "https://api.openf1.org/v1/car_data"
driver_url = "https://api.openf1.org/v1/drivers"
stint_url = "https://api.openf1.org/v1/stints"


def get_all_drivers_in_session(session_key: int) -> dict or None:
    """
    Function to get all drivers in a session. Creates a matching between each drivers number and their abbreviation.
    :param session_key: Number corresponding to a specific session.
    :return: Dictionary in which the keys are the drivers number and the value being their abbreviation.
    """
    params = {"session_key": session_key}
    r = requests.get(driver_url, params=params)
    if r.status_code != 200:
        print("Error with status code in driver data: ", r.status_code)
        return None
    driver_data = r.json()
    driver_df = pd.DataFrame(driver_data)
    driver_numbers = list(driver_df['driver_number'].unique())
    acronyms = list(driver_df['name_acronym'].unique())
    if len(driver_numbers) != len(acronyms):
        print("Number of drivers does not match number of acronyms")
        return None
    driver_matching = {int(x) : acronyms[driver_idx] for driver_idx, x in enumerate(driver_numbers)}
    print(acronyms)
    return driver_matching

def get_all_laps_in_session(session_key: int) -> dict or None:
    """
    Function that creates a dictionary containing all the lap data of all drivers in a selected session. Matches tire data from stint API endpoint correctly to the raw lap data from Laps API endpoint.
    :param session_key: Number corresponding to a specific session.
    :return: Dictionary of the following structure: driver_number : {"Lap Data" : DataFrame, "Driver Acronym" : str}
    """
    matching = get_all_drivers_in_session(session_key)
    driver_numbers = list(matching.keys())
    lap_data = {}
    for driver_number in driver_numbers:
        params = {"session_key": session_key, "driver_number": driver_number}
        lap_r = requests.get(lap_url, params=params)
        if lap_r.status_code == 429:
            data_could_not_be_loaded = True
            while data_could_not_be_loaded:
                print(f"Rate limit hit for driver {driver_number} | {matching[driver_number]}, retrying after 5 seconds...")
                for _ in tqdm(range(5)):
                    time.sleep(1)
                lap_r = requests.get(lap_url, params=params)
                if lap_r.status_code == 200:
                    data_could_not_be_loaded = False
        if lap_r.status_code != 200:
            print("Error with status code in lap data: ", lap_r.status_code)
            print(driver_number, matching[driver_number])
            return None

        driver_lap_data = lap_r.json()
        if not driver_lap_data: # Skips drivers for which no data is found, most of the time reserves that drove in P1
            print(f"No lap data for driver {driver_number} ({matching[driver_number]}), skipping...")
            continue

        driver_lap_df = pd.DataFrame(driver_lap_data)
        if driver_lap_df.empty:
            print(f"Empty lap dataframe for driver {driver_number} ({matching[driver_number]}), skipping...")
            continue

        driver_lap_df["actual_lap_time"] = round(driver_lap_df["duration_sector_1"] + driver_lap_df["duration_sector_2"] + driver_lap_df["duration_sector_3"], 3)
        driver_lap_df["Driver Acronym"] = matching[driver_number]
        color = get_driver_color(driver_number, session_key)
        driver_lap_df["Color"] = color
        driver_stints = get_driver_stint(session_key, driver_number)
        driver_lap_df, none_found = assign_tire_information_to_lap(driver_lap_df, driver_stints)
        if none_found:
            print(f"incomplete stint data for driver {driver_number} ({matching[driver_number]}), filled with None")
        lap_data[driver_number] = {"Lap Data" : driver_lap_df,
                               "Driver Acronym" : matching[driver_number]}
        lap_data = add_driver_fastest_session_lap_to_data(lap_data, driver_number)

    return lap_data

def add_driver_fastest_session_lap_to_data(data_dict: dict, driver_number: int) -> dict:
    """
    Creates a new key inside the main data dictionary and adds the fastest lap time of a driver in a specific session.
    :param data_dict: Main dictionary containing a drivers information about all laps in a specific session.
    :param driver_number: A drivers racing number.
    :return: Returns an updated version of the data dictionary containing the fastest lap time of a driver in a specific session under the key "Fastest Lap".
    """
    driver_lap_df = data_dict[driver_number]["Lap Data"]
    if not driver_lap_df["lap_duration"].dropna().empty:
        fastest_lap_index = driver_lap_df["lap_duration"].idxmin()
        fastest_lap_data = driver_lap_df.loc[fastest_lap_index]
        data_dict[driver_number]["Fastest Lap"] = fastest_lap_data
    else:
        print(f"All none values. No fastest lap found for driver {driver_number}")
    return data_dict

def get_driver_stint(session_key: int, driver_number: int) -> pd.DataFrame or None:
    """
    Function that extracts all driver stint data from a specified session.
    :param session_key: Number that corresponds to a specific session.
    :param driver_number: Number of a specific driver.
    :return: Returns a dataframe with all stint information of the driver in the given session
    """
    params = {"session_key": session_key, "driver_number": driver_number}
    stint_r = requests.get(stint_url, params=params)
    if stint_r.status_code == 429:
        data_could_not_be_loaded = True
        while data_could_not_be_loaded:
            print(f"Rate limit hit for driver {driver_number}, retrying after 5 seconds...")
            for _ in tqdm(range(5)):
                time.sleep(1)
            stint_r = requests.get(stint_url, params=params)
            if stint_r.status_code == 200:
                data_could_not_be_loaded = False

    elif stint_r.status_code != 200:
        print("Error with status code in stint data: ", stint_r.status_code)
        return None
    driver_stint_data = stint_r.json()
    driver_stint_df = pd.DataFrame(driver_stint_data)
    return driver_stint_df

def assign_tire_information_to_lap(lap_dataframe: pd.DataFrame, stint_dataframe: pd.DataFrame):
    """
    Function that adds the columns "Compound", "Tire Age" and "Stint Number" to the lap dataframe. It then extracts the tire data from the stint dataframe and matches it accordingly.
    :param lap_dataframe: Main dataframe containing a drivers lap data of a particular session. (openF1 Laps API endpoint)
    :param stint_dataframe: Stint dataframe containing driver stint information. (openF1 stint API endpoint)
    :return: Returns the updated version of "lap_dataframe" now containing information about the tire compound and age, as well as the driver's stint number.
    """
    lap_dataframe["Compound"] = None
    lap_dataframe["Tire Age"] = None
    lap_dataframe["Stint Number"] = None
    none_found = False
    for _, stint in stint_dataframe.iterrows():
        start_lap = stint["lap_start"]
        end_lap = stint["lap_end"]
        compound = stint["compound"]
        start_tire_age = stint["tyre_age_at_start"]
        stint_nr = stint["stint_number"]

        lap_mask = (lap_dataframe["lap_number"] >= start_lap) & (lap_dataframe["lap_number"] <= end_lap)
        lap_indices = lap_dataframe[lap_mask].index
        for i_lap, lap_index in enumerate(lap_indices):
            if compound is not None:
                lap_dataframe.at[lap_index, "Compound"] = compound
            else:
                none_found = True
                lap_dataframe.at[lap_index, "Compound"] = None

            if start_tire_age is not None:
                lap_dataframe.at[lap_index, "Tire Age"] = start_tire_age + i_lap
            else:
                none_found = True
                lap_dataframe.at[lap_index, "Tire Age"] = None

            if stint_nr is not None:
                lap_dataframe.at[lap_index, "Stint Number"] = stint_nr
            else:
                none_found = True
                lap_dataframe.at[lap_index, "Stint Number"] = None

    return lap_dataframe, none_found

def get_fastest_driver_order(data_dict: dict) -> List[Tuple[str, float]]:
    """
    Function that returns a list with tuples containing the driver acronym and their fastest session lap time in a sorted order.
    The first entry in the list is the fastest overall driver in that session.
    :param data_dict: Dictionary holding lap data from all drivers for a particular session.
    :return: List of tuples containing the driver acronym and their fastest session lap time.
    """
    fastest_lap_list = []
    for key, value in data_dict.items():
        fastest_lap_list.append((value["Driver Acronym"], float(value["Fastest Lap"]["lap_duration"])))
    result_list = sorted(fastest_lap_list, key=lambda x: x[1])
    return result_list

def compare_fastest_lap_characteristics(full_lap_df: pd.DataFrame, session_key: int) -> None:
    circuit, session_name = get_session_infos(session_key)
    fig, ax = plt.subplots(figsize=(12, 4))
    session_type = get_session_type(session_key)
    if session_type == "Qualifying":
        _, start_order = get_qualifying_results(full_lap_df, session_key)
        filtered_df = start_order
    else:
        filtered_df = full_lap_df.sort_values(by=["actual_lap_time", "date_start"], ascending=[True, True])
        filtered_df = filtered_df.drop_duplicates(subset=["driver_number"])
    filtered_df['bar_color'] = filtered_df['Compound'].map(COMPOUND_COLORS)
    plotting_df = filtered_df[filtered_df["actual_lap_time"].notna()]
    barplot = sns.barplot(plotting_df, y="actual_lap_time", x="Driver Acronym", hue="Driver Acronym", dodge=False,
        palette=plotting_df.set_index("Driver Acronym")["bar_color"].to_dict())

    for bar, (_, row) in zip(barplot.patches, plotting_df.iterrows()): # Annotate bar with lap time and used compound
        height = bar.get_height()
        x_pos = bar.get_x() + bar.get_width() / 2
        barplot.text(x=x_pos, y=height + 0.1, s=format_lap_time(height), ha='center', va='bottom', fontsize=9, rotation=90) # Lap Time
        barplot.text(x=x_pos, y=plotting_df["actual_lap_time"].iloc[0] * 0.96,s=row["Compound"].capitalize(),ha='center',va='bottom', fontsize=8,color='black') # Used Compound

    plt.xticks(rotation=45)
    if session_type == "Qualifying":
        # Vertical red dashed lines to separate the regions
        ax.axvline(9.5, color='black', linestyle='--', linewidth=0.75)   # Between Q3 and Q2
        ax.axvline(14.5, color='black', linestyle='--', linewidth=0.75)  # Between Q2 and Q1
        group_boundaries = [(0, 10, "Q3"), (10, 15, "Q2"), (15, 20, "Q1")]
        group_colors = ["#636363", "#222222", "#000000"]
        # Add shaded backgrounds and labels
        for (start, end, label), color in zip(group_boundaries, group_colors):
            ax.axvspan(start - 0.5, end - 0.5, color=color, alpha=0.3, zorder=0)
            # Calculate center of the shaded region
            center = (start + end - 1) / 2
            y_max = plotting_df["actual_lap_time"].max()
            # Add label above the bars (you can fine-tune y position)
            ax.text(center, y_max * 1.02, label, ha='center', va='bottom', fontsize=12, color='black')

    for label in ax.get_xticklabels():
        driver = label.get_text()
        color = plotting_df.loc[plotting_df["Driver Acronym"] == driver, "Color"].values[0]
        label.set_color("#" + color)
    ax.set_title(f"Circuit {circuit} - {session_name} fastest lap times")
    ax.set_ylim(plotting_df["actual_lap_time"].iloc[0] * 0.95, plotting_df["actual_lap_time"].iloc[-1] * 1.05)
    ax.set_ylabel("Lap Time")
    ax.set_xlabel("Driver")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: format_lap_time(x)))
    plt.show()


def match_laps_to_qualifying_session(lap_df: pd.DataFrame, session_key: int) -> pd.DataFrame:
    """
    Matches the correct qualifying session (Q1, Q2, Q3) to the driven laps to differentiate between lap times in qualifying.
    :param lap_df: Dataframe holding all driven laps during the whole qualifying session.
    :param session_key: Number corresponding to the qualifying session.
    :return: Returns updated Dataframe with laps matched to their corresponding qualifying sessions
    """
    # Get session start and end time from openF1 session API endpoint
    session_meta_url = f"https://api.openf1.org/v1/sessions?session_key={session_key}"
    ses_r = requests.get(session_meta_url)
    if ses_r.status_code != 200:
        raise Exception(f"Could not retrieve session metadata. Status code: {ses_r.status_code}")
    metadata = ses_r.json()
    if not metadata:
        raise Exception("Empty session metadata response.")

    session_info = metadata[0]
    session_start = pd.to_datetime(session_info["date_start"])
    session_end = pd.to_datetime(session_info["date_end"])
    if (session_end - session_start) > timedelta(minutes=70):
        # TODO: find way to segment qualy data during red flag sessions
        raise Exception("Session had red flags")

    # Define Q1-Q3 durations and the buffer between sessions --> Official F1 data
    q1_duration = timedelta(minutes=18)
    q1_buffer = timedelta(minutes=7)
    q2_duration = timedelta(minutes=15)
    q2_buffer = timedelta(minutes=8)
    # Set boundaries for start times to match laps into Q1-3
    q1_start = session_start
    q2_start = q1_start + q1_duration + q1_buffer
    q3_start = q2_start + q2_duration + q2_buffer

    lap_df = lap_df.copy()
    lap_df["date_start"] = pd.to_datetime(lap_df["date_start"])
    lap_df["Qualifying"] = None

    # Match laps to qualifying session
    lap_df.loc[lap_df["date_start"] < q2_start, "Qualifying"] = "Q1"
    lap_df.loc[(lap_df["date_start"] >= q2_start) & (lap_df["date_start"] < q3_start), "Qualifying"] = "Q2"
    lap_df.loc[lap_df["date_start"] >= q3_start, "Qualifying"] = "Q3"

    return lap_df

def get_session_type(session_key: int) -> str:
    url = f"https://api.openf1.org/v1/sessions?session_key={session_key}"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Failed to retrieve session data: {response.status_code}")
    data = response.json()
    if not data:
        raise ValueError("No session data found for the given session key.")

    return data[0].get("session_type", "Unknown") # "Unknown" acts as a fallback value


def get_session_infos(session_key: int):
    url = f"https://api.openf1.org/v1/sessions?session_key={session_key}"
    response = requests.get(url)
    if response.status_code != 200:
        raise Exception(f"Failed to retrieve session data: {response.status_code}")
    data = response.json()
    if not data:
        raise ValueError("No session data found for the given session key.")
    circuit = data[0].get("circuit_short_name", "Unknown")
    session_name = data[0].get("session_name", "Unknown")

    return circuit, session_name


def get_qualifying_results(lap_df: pd.DataFrame, session_key):
    session_type = get_session_type(session_key)
    if session_type != "Qualifying":
        raise ValueError(f"Invalid session type! The given session key must be of a qualifying session. Current session type: {session_type}")
    qualifying_data = match_laps_to_qualifying_session(lap_df, session_key)

    # Segment into qualifying sessions
    q1_df = qualifying_data[qualifying_data["Qualifying"] == "Q1"]
    q2_df = qualifying_data[qualifying_data["Qualifying"] == "Q2"]
    q3_df = qualifying_data[qualifying_data["Qualifying"] == "Q3"]
    qualifying_sessions = [q1_df, q2_df, q3_df]
    for list_idx, qualifying_session in enumerate(qualifying_sessions):
        qualifying_session = qualifying_session[qualifying_session["is_pit_out_lap"] == np.False_]
        # Use date_start as second sorting key in case of same lap times. --> First lap is the higher position
        qualifying_session = qualifying_session.sort_values(by=["actual_lap_time", "date_start"], ascending=[True, True])
        qualifying_session = qualifying_session.drop_duplicates(subset=["driver_number"])
        qualifying_sessions[list_idx] = qualifying_session

    last_5_drivers_q1 = qualifying_sessions[0].tail(5)
    last_5_drivers_q2 = qualifying_sessions[1].tail(5)
    qualifying_order = pd.concat([last_5_drivers_q2, last_5_drivers_q1])
    qualifying_order = pd.concat([qualifying_sessions[2], qualifying_order])
    return qualifying_sessions, qualifying_order


def get_driver_color(driver_number, session_key):
    url = f"https://api.openf1.org/v1/drivers?driver_number={driver_number}&session_key={session_key}"
    response = requests.get(url)
    if response.status_code == 429:
        data_could_not_be_loaded = True
        while data_could_not_be_loaded:
            print(f"Rate limit hit for driver {driver_number} during color extraction, retrying after 5 seconds...")
            for _ in tqdm(range(5)):
                time.sleep(1)
            response = requests.get(url)
            if response.status_code == 200:
                data_could_not_be_loaded = False
    elif response.status_code != 200:
        raise Exception(f"Failed to retrieve session data: {response.status_code}")
    data = response.json()
    if not data:
        raise ValueError("No session data found for the given session key.")
    return data[0].get("team_colour", "Unknown")


def format_lap_time(t):
    minutes = int(t // 60)
    seconds = int(t % 60)
    milliseconds = int((t - int(t)) * 1000)
    return f"{minutes}:{seconds:02d}.{milliseconds:03d}"