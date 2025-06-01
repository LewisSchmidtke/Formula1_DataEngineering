import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from fontTools.ttLib.woff2 import bboxFormat
from matplotlib.ticker import FuncFormatter

import fastf1 as f1
import fastf1.plotting as f1p


class RaceInfo:
    def __init__(self, year, event_name, session_number):
        self.schedule = f1.get_event_schedule(year)
        self.event = self.schedule.get_event_by_name(event_name)
        self.session = self.event.get_session(session_number)
        self.session.load()
        self.session_lap_data = self.session.laps

        self.compound_info = {
            "SOFT": "#FF0000",    # Red
            "MEDIUM": "#FFD800",  # Yellow
            "HARD": "#808080",     # Dark grey
            "INTERMEDIATE": "#00A550", # Green
            "WET" : "#0072C6", # Blue
        }
        self.ignored_compounds = {"TEST_UNKNOWN" : "#0000000",
                                  "UNKNOWN" : "#000000"}

    @staticmethod
    def format_lap(td):
        if pd.isnull(td):
            return ""
        total_seconds = int(td.total_seconds())
        millis = int(td.microseconds / 1000)
        mins, secs = divmod(total_seconds, 60)
        return f"{mins:02}:{secs:02}.{millis:03}"

    @staticmethod
    def format_seconds_to_time(seconds, pos):
        if pd.isna(seconds):
            return ""
        mins = int(seconds // 60)
        secs = seconds % 60
        return f"{mins:01}:{secs:05.2f}"




class LapTimePlotByTireAndSession(RaceInfo):
    def __init__(self, year, event_name, session_number, figsize=(16,8)):
        super().__init__(year, event_name, session_number)

        # Initializing attributes
        self.average_lap_data = {}
        self.df = None
        self.session_compounds = []
        self.drivers = []
        self.fig, self.ax = plt.subplots(figsize=figsize)

        # Data processing
        self.fill_average_lap_data()
        self.create_dataframe()

        self.x = np.arange(len(self.drivers))
        self.bar_width = 0.25

        self.create_bars()
        self.set_plot_aesthetic()
        self.adjust_y_range()

    def fill_average_lap_data(self):
        for driver_nr in self.session.drivers:
            # Extract driver info to get abbreviation
            driver_info = self.session.get_driver(driver_nr)
            driver_abbreviation = driver_info["Abbreviation"]
            # Extract subframe with only laps driven by driver
            driver_laps = self.session_lap_data[self.session_lap_data["Driver"] == driver_abbreviation]
            filtered_driver_laps = driver_laps[driver_laps["LapTime"].notna()] # Removes laps without lap time
            # Removes laps that don't have correct tire compound
            filtered_laps_by_compound = filtered_driver_laps[~filtered_driver_laps["Compound"].isin(self.ignored_compounds)]
            # Calculates average lap time based on tire compound
            average_lap_time_tire = filtered_laps_by_compound.groupby("Compound")["LapTime"].mean()
            self.average_lap_data[driver_abbreviation] = average_lap_time_tire

    def create_dataframe(self):
        self.df = pd.DataFrame(self.average_lap_data).T # Transpose so drivers are rows and compounds are columns
        self.session_compounds = list(self.df.columns)
        # Index reset and column rename
        self.df = self.df.reset_index().melt(id_vars="index", value_vars=self.session_compounds, var_name="Compound", value_name="LapTime")
        self.df.rename(columns={"index": "Driver"}, inplace=True)

        # Sort drivers based on medium compound times
        medium_compound_sorted = self.df[self.df["Compound"] == "MEDIUM"].groupby("Driver")["LapTime"].min()
        self.df['SortKey'] = self.df['Driver'].map(medium_compound_sorted)
        self.df = self.df.sort_values(by=['SortKey', 'Driver']).drop(columns='SortKey').reset_index(drop=True)

        self.drivers = self.df["Driver"].unique() # Extract drivers in session
        self.df['LapStr'] = self.df['LapTime'].apply(self.format_lap) # Converts to MM:ss:mmm for display
        self.df["LapTime"] = self.df["LapTime"].dt.total_seconds() # Converts to total seconds for math

    def create_bars(self):
        multiplier = 0
        for compound in self.compound_info: # Iterate over all possible tires
            if compound not in self.session_compounds: # Skip if no driver used a specific compound
                continue
            # Manipulates df so that all compound data by fastest medium driver is together
            compound_data = self.df[self.df['Compound'] == compound].set_index('Driver').reindex(self.drivers)
            lap_times = compound_data['LapTime'].values

            offset = self.bar_width * multiplier
            bars = self.ax.bar(self.x + offset, lap_times, self.bar_width,label=compound, color=self.compound_info[compound], edgecolor='black', linewidth=0.5, alpha=0.8)
            for i, (bar, time) in enumerate(zip(bars, lap_times)):
                if pd.isna(time):
                    continue
                formatted_time = compound_data.loc[self.drivers[i], 'LapStr'] # Get display time of driver
                self.ax.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.2, formatted_time, ha='center', va='bottom', fontsize=8, rotation=90)
            multiplier += 1

    def set_plot_aesthetic(self):
        self.ax.set_title(f"{self.session}: Average Lap Times by Driver and Tire Compound")
        self.ax.legend(title="Tire Compound", bbox_to_anchor=(-0.05, 1))
        self.ax.grid(True, alpha=0.2, axis='both', color='gray', linewidth=1) # Change grid
        self.ax.set_xlabel("Driver", fontsize=12, fontweight='bold')
        self.ax.set_xticks(self.x + self.bar_width)
        self.ax.set_ylabel('Lap Time (seconds)', fontsize=12, fontweight='bold')
        # Driver abbreviation with driver color
        labels = self.ax.set_xticklabels(self.drivers, rotation=45, ha='right')
        for i, driver in enumerate(self.drivers):
            driver_color = f1p.get_driver_color(driver, self.session)
            labels[i].set_color(driver_color)

    def adjust_y_range(self):
        if len(self.df["LapTime"]) > 0:
            min_lap_time = self.df["LapTime"].min()
            max_lap_time = self.df["LapTime"].max()
            time_range = max_lap_time - min_lap_time
            padding = time_range * 0.2
            self.ax.set_ylim(min_lap_time - padding * 2, max_lap_time + padding) # Higher bottom padding for better aesthetics
        self.ax.yaxis.set_major_formatter(FuncFormatter(self.format_seconds_to_time))
        plt.tight_layout()