from src.data_processing import *

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

def visualize_lap_telemetry(single_lap_telemetry_df: pd.DataFrame) -> None:
    fig, ax = plt.subplots(nrows=2, ncols=1, sharex=True, figsize=(13, 4))
    sns.lineplot(data=single_lap_telemetry_df, x="seconds_from_lap_start", y="speed", ax=ax[0])
    sns.lineplot(data=single_lap_telemetry_df, x="seconds_from_lap_start", y="throttle", ax=ax[1], color='g')
    sns.lineplot(data=single_lap_telemetry_df, x="seconds_from_lap_start", y="brake", ax=ax[1], color='r')

    fig.suptitle('Lap telemetry')
    ax[0].set_ylabel("Vehicle Speed \ km/h")
    ax[1].set_ylabel('Throttle and Brake \ %')
    ax[1].xaxis.set_major_formatter(FuncFormatter(lambda x, _: format_lap_time(x)))