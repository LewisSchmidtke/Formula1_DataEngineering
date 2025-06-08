import time

import pandas as pd
import requests
import logging

from tqdm import tqdm

logging.basicConfig(level=logging.INFO)



class Session:
    def __init__(self, session_key):
        self.session_key = session_key

        self.SESSION_URL = f"https://api.openf1.org/v1/sessions?session_key={self.session_key}"
        self.LAP_URL = "https://api.openf1.org/v1/laps"
        self.CAR_URL = "https://api.openf1.org/v1/car_data"
        self.DRIVER_URL = "https://api.openf1.org/v1/drivers"
        self.STINT_URL = "https://api.openf1.org/v1/stints"

        self.COMPOUND_INFO = {
            "SOFT": "#FF0000",        # Red
            "MEDIUM": "#FFD800",      # Yellow
            "HARD": "#808080",        # Dark grey
            "INTERMEDIATE": "#00A550",# Green
            "WET": "#0072C6",         # Blue
        }

        self.session_type = None
        self.session_circuit = None
        self.session_name = None
        self.get_session_info() # Sets the correct values for the 3 attributes above

        self.session_lap_data_dict = {}
        self.get_session_laps_data() # Fills data dict

        self.session_fastest_laps = None
        self.get_fastest_session_lap_for_each_driver() # Sets df to session_fastest_laps



    @staticmethod
    def check_request(response, url, params=None):
        # Enter delay loop if error code 429
        while response.status_code == 429: # Error code 429 is rate limit of api calls reached
            logging.warning("Rate Limit Exceeded, trying again in 5 seconds...")
            for _ in tqdm(range(5)): # tqdm to keep loading bar
                time.sleep(1)
            if params is None:
                response = requests.get(url) # try again
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

    @staticmethod
    def assign_tire_information_to_lap(driver_lap_df, driver_stints_df):
        # Will apply "merge_asof" both dfs need to be sorted
        driver_lap_df = driver_lap_df.sort_values("lap_number").reset_index(drop=True)
        driver_stints_df = driver_stints_df.sort_values("lap_start").reset_index(drop=True)

        # direction=backward important to match current lap to last stint lap
        merged = pd.merge_asof(driver_lap_df, driver_stints_df, left_on="lap_number", right_on="lap_start",
                               direction="backward")

        # Filter out laps beyond the end of the stint
        in_stint = merged["lap_number"] <= merged["lap_end"]
        merged.loc[~in_stint, ["compound", "tyre_age_at_start", "stint_number"]] = None
        # Calculate Tire Age for valid rows and set none based on invalid filter from above
        merged["Tire Age"] = merged["lap_number"] - merged["lap_start"] + merged["tyre_age_at_start"]
        merged.loc[~in_stint | merged["tyre_age_at_start"].isna(), "Tire Age"] = None

        # Rename and assign final columns
        driver_lap_df["Compound"] = merged["compound"]
        driver_lap_df["Stint Number"] = merged["stint_number"]
        driver_lap_df["Tire Age"] = merged["Tire Age"]

        # Check for incomplete data
        incomplete_data_bool = merged[["compound", "tyre_age_at_start", "stint_number"]].isna().any(axis=1).any()

        return driver_lap_df, incomplete_data_bool

    def get_session_info(self):
        session_response = requests.get(self.SESSION_URL)
        session_data = self.check_request(session_response, self.SESSION_URL)
        # Set attributes with current session data
        self.session_circuit = session_data[0].get("circuit_short_name", "Unknown")
        self.session_name = session_data[0].get("session_name", "Unknown")
        self.session_type = session_data[0].get("session_type", "Unknown")

    def get_specific_driver_data(self, driver_number):
        driver_url = self.DRIVER_URL + f"?driver_number={driver_number}&session_key={self.session_key}"
        driver_response = requests.get(driver_url)
        driver_data = self.check_request(driver_response, driver_url)
        driver_number = driver_data[0].get("driver_number", "Unknown")
        driver_acronym = driver_data[0].get("name_acronym", "Unknown")
        driver_color = driver_data[0].get("driver_color", "Unknown")

        return driver_number, driver_acronym, driver_color

    def drivers_match_numbers_to_acronyms(self):
        all_drivers_url = self.DRIVER_URL + f"?session_key={self.session_key}"
        all_drivers_response = requests.get(all_drivers_url)
        all_drivers = self.check_request(all_drivers_response, all_drivers_url)

        all_driver_df = pd.DataFrame(all_drivers)
        driver_numbers = list(all_driver_df["driver_number"].unique())
        driver_acronyms = list(all_driver_df["name_acronym"].unique())

        driver_matching = {int(number) : driver_acronyms[driver_idx] for driver_idx, number in enumerate(driver_numbers)}
        return driver_matching

    def get_driver_stints(self, driver_number):
        driver_stint_url = self.STINT_URL + f"?session_key={self.session_key}&driver_number={driver_number}"
        driver_stint_response = requests.get(driver_stint_url)
        driver_stints_data = self.check_request(driver_stint_response, driver_stint_url)
        driver_stints_df = pd.DataFrame(driver_stints_data)

        return driver_stints_df

    def get_session_laps_data(self):
        matching = self.drivers_match_numbers_to_acronyms()
        for driver_number, driver_acronym in matching.items():
            driver_lap_url = self.LAP_URL + f"?session_key={self.session_key}&driver_number={driver_number}"
            driver_lap_response = requests.get(driver_lap_url)
            driver_lap_data = self.check_request(driver_lap_response, driver_lap_url)
            driver_lap_df = pd.DataFrame(driver_lap_data)

            # Actual lap time needs to be calculated - column with lap duration not accurate
            driver_lap_df["actual_lap_time"] = round(driver_lap_df["duration_sector_1"] + driver_lap_df["duration_sector_2"] + driver_lap_df["duration_sector_3"], 3)
            driver_lap_df["Driver Acronym"] = driver_acronym # Add driver acronym
            _, _, driver_color = self.get_specific_driver_data(driver_number)
            driver_lap_df["Driver Color"] = driver_color # Add driver color

            # Extract stint and tire data
            driver_stints_df = self.get_driver_stints(driver_number)
            driver_lap_df, incomplete_data_bool = self.assign_tire_information_to_lap(driver_lap_df, driver_stints_df)
            if incomplete_data_bool:
                logging.warning(f"Incomplete stint data found for driver number {driver_number} | {driver_acronym}.")
            self.session_lap_data_dict[driver_number] = driver_lap_df

    def get_fastest_session_lap_for_each_driver(self):
        fastest_laps = []
        for driver_number in self.session_lap_data_dict.keys():
            driver_session_df = self.session_lap_data_dict[driver_number]
            if not driver_session_df["actual_lap_time"].dropna().empty:
                fastest_lap_index = driver_session_df["actual_lap_time"].dropna().idxmin()
                fastest_lap_data = driver_session_df.loc[fastest_lap_index]
                fastest_laps.append(fastest_lap_data)

        self.session_fastest_laps = pd.DataFrame(fastest_laps)

    def get_session_position_order(self):
        if self.session_fastest_laps is None:
            logging.warning(f"No fastest lap data found, make sure to call get_fastest_session_lap_for_each_driver before.")
            return None
        fastest_laps = self.session_fastest_laps
        # Sorts by fastest lap time first and by which lap was started first as a tie-breaker.
        fastest_laps = fastest_laps.sort_values(by=["actual_lap_time", "date_start"], ascending=[True, True])
        return fastest_laps

    def get_lap_telemetry_data(self, lap_number, driver_number):
        if self.session_lap_data_dict[driver_number] is None:
            logging.warning(f"No lap data found for driver number {driver_number}.")
            return None
        if lap_number not in self.session_lap_data_dict[driver_number]["lap_number"].values:
            logging.warning(f"Lap number {lap_number} not found in session lap data.")
            return None

        # Calculate time bounds for telemetry
        raw_start_time = self.session_lap_data_dict[driver_number]["date_start"].loc[lap_number]
        raw_lap_duration = self.session_lap_data_dict[driver_number]["actual_lap_time"].loc[lap_number]
        lap_start_time = pd.to_datetime(raw_start_time)
        lap_duration = pd.to_timedelta(float(raw_lap_duration), unit='s')
        lap_end_time = lap_start_time + lap_duration

        params={"session_key": self.session_key, "driver_number": driver_number}
        car_response = requests.get(self.CAR_URL, params=params)
        car_data = self.check_request(car_response, self.CAR_URL, params)
        car_df = pd.DataFrame(car_data)
        car_df["date"] = pd.to_datetime(car_df["date"], format="ISO8601")
        # Add column with lap seconds for plotting
        car_df["seconds_from_lap_start"] = (car_df["date"] - lap_start_time).dt.total_seconds()

        filtered_df = car_df[(car_df["date"] >= lap_start_time) & (car_df["date"] <= lap_end_time)]

        return filtered_df




    # TODO: function for getting telemetry of fastest lap
    # TODO: function for position data
    # TODO: function for race position changes from Position API
    # TODO: function for pit data (average and laps during race








