import time

import pandas as pd
import requests
import logging

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import seaborn as sns

import src.helper_functions as helper
import src.data_processing as dp

logging.basicConfig(level=logging.INFO)

COMPOUND_COLORS = {
    "SOFT": "#FF0000",        # Red
    "MEDIUM": "#FFD800",      # Yellow
    "HARD": "#808080",        # Dark grey
    "INTERMEDIATE": "#00A550",# Green
    "WET": "#0072C6",         # Blue
}

class Session:
    def __init__(self, session_key):
        self.session_key = session_key

        self.SESSION_URL = f"https://api.openf1.org/v1/sessions?session_key={self.session_key}"
        self.LAP_URL = "https://api.openf1.org/v1/laps"
        self.CAR_URL = "https://api.openf1.org/v1/car_data"
        self.DRIVER_URL = "https://api.openf1.org/v1/drivers"
        self.STINT_URL = "https://api.openf1.org/v1/stints"
        self.PIT_URL = "https://api.openf1.org/v1/pit"
        self.LOCATION_URL = "https://api.openf1.org/v1/location"

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

    @staticmethod
    def convert_col_to_datetime(df, col):
        df[col] = pd.to_datetime(df[col], format="ISO8601")
        return df

    @staticmethod
    def create_seconds_from_start_col(df, start_time):
        df["seconds_from_lap_start"] = (df["date"] - start_time).dt.total_seconds()
        return df

    @staticmethod
    def apply_time_mask_to_df(df, start_time, end_time):
        masked_df = df[(df["date"] >= start_time) & (df["date"] <= end_time)]
        return masked_df

    def get_session_info(self):
        session_response = requests.get(self.SESSION_URL)
        session_data = helper.check_request(session_response, self.SESSION_URL)
        # Set attributes with current session data
        self.session_circuit = session_data[0].get("circuit_short_name", "Unknown")
        self.session_name = session_data[0].get("session_name", "Unknown")
        self.session_type = session_data[0].get("session_type", "Unknown")

    def get_specific_driver_data(self, driver_number):
        driver_url = self.DRIVER_URL + f"?driver_number={driver_number}&session_key={self.session_key}"
        driver_response = requests.get(driver_url)
        driver_data = helper.check_request(driver_response, driver_url)
        driver_number = driver_data[0].get("driver_number", "Unknown")
        driver_acronym = driver_data[0].get("name_acronym", "Unknown")
        driver_color = driver_data[0].get("driver_color", "Unknown")

        return driver_number, driver_acronym, driver_color

    def drivers_match_numbers_to_acronyms(self):
        all_drivers_url = self.DRIVER_URL + f"?session_key={self.session_key}"
        all_drivers_response = requests.get(all_drivers_url)
        all_drivers = helper.check_request(all_drivers_response, all_drivers_url)

        all_driver_df = pd.DataFrame(all_drivers)
        driver_numbers = list(all_driver_df["driver_number"].unique())
        driver_acronyms = list(all_driver_df["name_acronym"].unique())

        driver_matching = {int(number) : driver_acronyms[driver_idx] for driver_idx, number in enumerate(driver_numbers)}
        return driver_matching

    def get_driver_stints(self, driver_number):
        driver_stint_url = self.STINT_URL + f"?session_key={self.session_key}&driver_number={driver_number}"
        driver_stint_response = requests.get(driver_stint_url)
        driver_stints_data = helper.check_request(driver_stint_response, driver_stint_url)
        driver_stints_df = pd.DataFrame(driver_stints_data)

        return driver_stints_df

    def get_session_laps_data(self):
        matching = self.drivers_match_numbers_to_acronyms()
        for driver_number, driver_acronym in matching.items():
            driver_lap_url = self.LAP_URL + f"?session_key={self.session_key}&driver_number={driver_number}"
            driver_lap_response = requests.get(driver_lap_url)
            driver_lap_data = helper.check_request(driver_lap_response, driver_lap_url)
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

    def get_lap_start_and_end_time(self, lap_number, driver_number, fastest_lap=False):
        if not fastest_lap:
            raw_start_time = self.session_lap_data_dict[driver_number]["date_start"].loc[lap_number]
            raw_lap_duration = self.session_lap_data_dict[driver_number]["actual_lap_time"].loc[lap_number]
        else:  # directly access fastest lap data
            raw_start_time = self.session_fastest_laps.loc[
                self.session_fastest_laps["driver_number"] == driver_number, "date_start"].iloc[0]
            raw_lap_duration = self.session_fastest_laps.loc[
                self.session_fastest_laps["driver_number"] == driver_number, "actual_lap_time"].iloc[0]

        # Calculate time bounds for telemetry
        lap_start_time = pd.to_datetime(raw_start_time)
        lap_duration = pd.to_timedelta(float(raw_lap_duration), unit='s')
        lap_end_time = lap_start_time + lap_duration

        return lap_start_time, lap_duration, lap_end_time

    def get_lap_telemetry_data(self, lap_number, driver_number, fastest_lap=False):
        """
        Function to get the car telemetry data for a given driver and lap number. If fastest_lap is set to True, ignores the lap number.
        :param lap_number:
        :param driver_number:
        :param fastest_lap:
        :return:
        """
        if self.session_lap_data_dict[driver_number] is None:
            logging.warning(f"No lap data found for driver number {driver_number}.")
            return None
        if lap_number not in self.session_lap_data_dict[driver_number]["lap_number"].values:
            logging.warning(f"Lap number {lap_number} not found in session lap data.")
            return None

        lap_start_time, lap_duration, lap_end_time = self.get_lap_start_and_end_time(lap_number, driver_number, fastest_lap)

        params={"session_key": self.session_key, "driver_number": driver_number}
        car_response = requests.get(self.CAR_URL, params=params)
        car_data = helper.check_request(car_response, self.CAR_URL, params)
        car_df = pd.DataFrame(car_data)
        car_df = self.convert_col_to_datetime(car_df, "date")
        car_df = self.create_seconds_from_start_col(car_df, lap_start_time)
        filtered_df = self.apply_time_mask_to_df(car_df, lap_start_time, lap_end_time)

        return filtered_df

    def get_driver_pit_data(self, driver_number):
        pit_url = self.PIT_URL + f"?driver_number={driver_number}&session_key={self.session_key}"
        pit_response = requests.get(pit_url)
        pit_data = helper.check_request(pit_response, pit_url)
        pit_data_df = pd.DataFrame(pit_data)
        pit_data_df = pit_data_df.drop(columns=["meeting_key", "session_key"])
        return pit_data_df

    def get_track_position_for_lap(self, lap_number, driver_number, fastest_lap=False):
        lap_start_time, lap_duration, lap_end_time = self.get_lap_start_and_end_time(lap_number, driver_number, fastest_lap)
        location_url = self.LOCATION_URL + f"?driver_number={driver_number}&session_key={self.session_key}"
        location_response = requests.get(location_url)
        location_data = helper.check_request(location_response, location_url)
        location_df = pd.DataFrame(location_data)
        location_df = self.convert_col_to_datetime(location_df, "date")
        location_df = self.create_seconds_from_start_col(location_df, lap_start_time)
        filtered_df = self.apply_time_mask_to_df(location_df, lap_start_time, lap_end_time)

        return filtered_df

    def match_track_position_and_gear(self, lap_number, driver_number, fastest_lap=False):
        lap_telemetry_df = self.get_lap_telemetry_data(lap_number, driver_number, fastest_lap)
        lap_track_pos_df = self.get_track_position_for_lap(lap_number, driver_number, fastest_lap)

        lap_telemetry_df = lap_telemetry_df.sort_values("date").reset_index(drop=True)
        lap_track_pos_df = lap_track_pos_df.sort_values("date").reset_index(drop=True)

        # direction=nearest to match date entries to the closest match
        merged_df = pd.merge_asof(lap_telemetry_df, lap_track_pos_df, on="date", direction="nearest")

        return merged_df

    def create_full_session_df(self):
        combined_laps = pd.concat(
            [v for v in self.session_lap_data_dict.values()],
            ignore_index=True
        )
        return combined_laps

    def compare_fastest_lap_characteristics(self):
        fig, ax = plt.subplots(figsize=(12, 4))
        full_lap_df = self.create_full_session_df()
        if self.session_type == "Qualifying":
            _, start_order = dp.get_qualifying_results(full_lap_df, self.session_key)
            filtered_df = start_order
        else:
            filtered_df = full_lap_df.sort_values(by=["actual_lap_time", "date_start"], ascending=[True, True])
            filtered_df = filtered_df.drop_duplicates(subset=["driver_number"])
        filtered_df['bar_color'] = filtered_df['Compound'].map(COMPOUND_COLORS)
        plotting_df = filtered_df[filtered_df["actual_lap_time"].notna()]
        barplot = sns.barplot(plotting_df, y="actual_lap_time", x="Driver Acronym", hue="Driver Acronym", dodge=False,
                              palette=plotting_df.set_index("Driver Acronym")["bar_color"].to_dict())

        for bar, (_, row) in zip(barplot.patches,
                                 plotting_df.iterrows()):  # Annotate bar with lap time and used compound
            height = bar.get_height()
            x_pos = bar.get_x() + bar.get_width() / 2
            barplot.text(x=x_pos, y=height + 0.1, s=helper.format_lap_time(height), ha='center', va='bottom', fontsize=9,
                         rotation=90)  # Lap Time
            barplot.text(x=x_pos, y=plotting_df["actual_lap_time"].iloc[0] * 0.96, s=row["Compound"].capitalize(),
                         ha='center', va='bottom', fontsize=8, color='black')  # Used Compound

        plt.xticks(rotation=45)
        if self.session_type == "Qualifying":
            # Vertical dashed lines to separate the regions
            ax.axvline(9.5, color='black', linestyle='--', linewidth=0.75)  # Between Q3 and Q2
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
            color = plotting_df.loc[plotting_df["Driver Acronym"] == driver, "Driver Color"].values[0]
            if color == "Unknown":
                color = "#000000"
            label.set_color(color)
        ax.set_title(f"Circuit {self.session_circuit} - {self.session_name} fastest lap times")
        ax.set_ylim(plotting_df["actual_lap_time"].iloc[0] * 0.95, plotting_df["actual_lap_time"].iloc[-1] * 1.05)
        ax.set_ylabel("Lap Time")
        ax.set_xlabel("Driver")
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: helper.format_lap_time(x)))
        plt.tight_layout()

        return fig






    # TODO: function for race position changes from Position API
    # TODO: implement gear shift map correctly with telemetry
    # TODO: Lap time development chart during session
