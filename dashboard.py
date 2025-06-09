import streamlit as st

import matplotlib.pyplot as plt

import src.helper_functions as helper
from src.session_object import Session

# Page configuration
st.set_page_config(
    page_title="Formula 1 Data Dashboard",
    page_icon="🏎️",
    layout="wide"
)

# Title
st.title("🏎️ Formula 1 Data Dashboard")
st.markdown("---")


# Initialize session state
if 'selected_year' not in st.session_state:
    st.session_state.selected_year = None
if 'selected_weekend' not in st.session_state:
    st.session_state.selected_weekend = None
if 'selected_session' not in st.session_state:
    st.session_state.selected_session = None
if 'session_object' not in st.session_state:
    st.session_state.session_object = None
if 'current_session_key' not in st.session_state:
    st.session_state.current_session_key = None

# Year input section
col1, col2 = st.columns([1, 3])

with col1:
    year_input = st.number_input(
        "Enter Calendar Year:",
        min_value=2000,
        max_value=2025,
        value=2025,
        step=1,
        key="year_input"
    )

meeting_key = 0000
session_key = 0000
# Weekend dropdown (appears after year is entered)
if year_input:
    st.session_state.selected_year = year_input
    weekend_tuples = helper.get_f1_weekends(year_input)
    weekends = [tup[0] for tup in weekend_tuples]

    with col2:
        if weekends:
            selected_weekend = st.selectbox(
                "Select Formula 1 Weekend:",
                options=[""] + weekends,
                key="weekend_select"
            )

            if selected_weekend:
                st.session_state.selected_weekend = selected_weekend
                meeting_key = weekend_tuples[weekends.index(selected_weekend)][1]
        else:
            st.warning(f"No Formula 1 weekends found for year {year_input}")

# Session selection (appears after weekend is selected)
if st.session_state.selected_weekend:
    st.markdown("---")
    st.subheader(f"📅 {st.session_state.selected_weekend}")

    # Create session buttons in a horizontal row
    session_tuples = helper.get_sessions_in_weekend(meeting_key=meeting_key)
    sessions = [tup[0] for tup in session_tuples]

    cols = st.columns(5)

    for i, session in enumerate(sessions):
        with cols[i]:
            if st.button(
                    session,
                    key=f"session_{i}",
                    use_container_width=True,
                    type="primary" if st.session_state.selected_session == session else "secondary"
            ):
                st.session_state.selected_session = session
                session_key = session_tuples[sessions.index(session)][1]

                # Only create session object if it's a different session to avoid recreating unnecessarily
                if st.session_state.current_session_key != session_key:
                    with st.spinner(f'Loading {session} data...'):
                        try:
                            st.session_state.session_object = Session(session_key)
                            st.session_state.current_session_key = session_key
                            st.success(f'✅ {session} data loaded successfully!')
                        except Exception as e:
                            st.error(f'❌ Error loading session data: {str(e)}')
                            st.session_state.session_object = None
                            st.session_state.current_session_key = None

if 'session_object' in st.session_state and st.session_state.session_object:
    st.markdown("---")
    st.subheader("📊 Session Information")

    session_obj = st.session_state.session_object
    fig = session_obj.compare_fastest_lap_characteristics()
    st.pyplot(fig)
    plt.close(fig)  # Close the figure to free memory



# Footer
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: gray;'>© 2025 Lewis M. Schmidtke. All Rights Reserved.</div>",
    unsafe_allow_html=True
)