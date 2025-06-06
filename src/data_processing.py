import time
import requests
import pandas as pd

from typing import List, Tuple

from tqdm import tqdm


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
        driver_lap_df = pd.DataFrame(driver_lap_data)

        driver_stints = get_driver_stint(session_key, driver_number)
        driver_lap_df = assign_tire_information_to_lap(driver_lap_df, driver_stints)

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
    fastest_lap_data = driver_lap_df.loc[driver_lap_df["lap_duration"].idxmin()]
    data_dict[driver_number]["Fastest Lap"] = fastest_lap_data

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


def assign_tire_information_to_lap(lap_dataframe: pd.DataFrame, stint_dataframe: pd.DataFrame) -> pd.DataFrame:
    """
    Function that adds the columns "Compound", "Tire Age" and "Stint Number" to the lap dataframe. It then extracts the tire data from the stint dataframe and matches it accordingly.
    :param lap_dataframe: Main dataframe containing a drivers lap data of a particular session. (openF1 Laps API endpoint)
    :param stint_dataframe: Stint dataframe containing driver stint information. (openF1 stint API endpoint)
    :return: Returns the updated version of "lap_dataframe" now containing information about the tire compound and age, as well as the driver's stint number.
    """
    lap_dataframe["Compound"] = None
    lap_dataframe["Tire Age"] = None
    lap_dataframe["Stint Number"] = None

    for _, stint in stint_dataframe.iterrows():
        start_lap = stint["lap_start"]
        end_lap = stint["lap_end"]
        compound = stint["compound"]
        start_tire_age = stint["tyre_age_at_start"]
        stint_nr = stint["stint_number"]

        lap_mask = (lap_dataframe["lap_number"] >= start_lap) & (lap_dataframe["lap_number"] <= end_lap)
        lap_indices = lap_dataframe[lap_mask].index
        for i_lap, lap_index in enumerate(lap_indices):
            lap_dataframe.at[lap_index, "Compound"] = compound
            lap_dataframe.at[lap_index, "Tire Age"] = start_tire_age + i_lap
            lap_dataframe.at[lap_index, "Stint Number"] = stint_nr

    return lap_dataframe


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