<<<<<<< HEAD
import streamlit as st
from macros_calculator import load_data, save_meal

load_data()
st.title("Macros Calculator")
tab1, tab2, tab3, tab4 = st.tabs(["Calculate Macros", "Display Stored Meals", "Display total Calorie and Protein Intake", "Calculate Average Calorie and Protein Intake"])

with tab1:

    option = st.radio("Select an option", ("Calculate Macros for Single Item", "Calculate Macros for Multiple Items"))

    if option == "Calculate Macros for Single Item":
        weight = st.number_input("Enter the weight of the food item (in grams)", min_value=0)
        serving_size = st.number_input("Enter the serving size (in grams)", min_value=1)
        calories = st.number_input("Enter the calories per serving", min_value=1)
        protein = st.number_input("Enter the protein per serving (in grams)", min_value=1)

        if st.button("Calculate"):
            if weight > 0:
                total_calories = weight/serving_size*calories
                total_protein = weight/serving_size*protein
                st.success(f"Calories: {total_calories:.2f}, Protein: {total_protein:.2f}g")
            else:
                st.error("Weight must be greater than 0.")

        if st.button("Save Meal"):
            date = st.date_input("Select date")
            name = st.text_input("Enter the name of the meal")
            save_meal(name, date, total_calories, total_protein) # Need to implement session state to store these values

    #elif option == "Calculate Macros for Multiple Items":
=======
import streamlit as st
import pandas as pd
import altair as alt
from datetime import date

from macros_calculator import (
    init_db,
    calculate_single_item,
    calculate_multiple_items,
    insert_meal,
    get_meals_by_date,
    get_day_totals,
    get_daily_summary,
    get_average_between_dates
)

# ======================================================
# APP CONFIGURATION
# ======================================================

st.set_page_config(
    page_title="Macros Calculator",
    page_icon="🍽️",
    layout="wide"
)

init_db()

# Session State
if "multi_items" not in st.session_state:
    st.session_state.multi_items = []

if "last_result" not in st.session_state:
    st.session_state.last_result = None


# ======================================================
# SIDEBAR
# ======================================================

with st.sidebar:
    st.header("🏋️ Macros Calculator")
    st.write(
        "Track calories & protein intake to support "
        "your fitness goals."
    )
    st.divider()
    st.write("📌 Features")
    st.write("• Single & multi-item meals")
    st.write("• Daily totals & trends")
    st.write("• SQLite-based persistence")
    st.divider()
    st.caption("Built with Python & Streamlit")


# ======================================================
# MAIN TITLE
# ======================================================

st.title("🍽️ Macros Calculator")
st.caption("A clean, analytics-driven nutrition tracking app")

tab1, tab2, tab3, tab4 = st.tabs([
    "🧮 Single Item",
    "🥗 Multiple Items",
    "📅 Daily Summary",
    "📊 Analytics"
])


# ======================================================
# TAB 1 — SINGLE ITEM
# ======================================================

with tab1:
    st.subheader("🧮 Single Item Macro Calculator")

    with st.container():
        st.markdown("### Nutrition Input")

        col1, col2 = st.columns(2)
        with col1:
            weight = st.number_input("Weight (g)", min_value=0.0)
            serving = st.number_input("Serving Size (g)", min_value=1.0)

        with col2:
            calories = st.number_input("Calories per Serving", min_value=0.0)
            protein = st.number_input("Protein per Serving (g)", min_value=0.0)

    with st.container():
        st.markdown("### Meal Details")

        col1, col2 = st.columns(2)
        with col1:
            meal_name = st.text_input("Meal Name", key="single_meal_name")
        with col2:
            meal_date = st.date_input("Meal Date", value=date.today(), key="single_meal_date")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Calculate Macros", type="primary", key="calc_single"):
            try:
                cal, pro = calculate_single_item(
                    weight, serving, calories, protein
                )
                st.session_state.last_result = {
                    "calories": cal,
                    "protein": pro
                }
                st.success(f"Calories: {cal} kcal | Protein: {pro} g")
            except ValueError as e:
                st.error(str(e))

    with col2:
        if st.button("Save Meal", type="primary", key="save_single"):
            if st.session_state.last_result is None:
                st.error("Please calculate macros before saving.")
            else:
                insert_meal(
                    meal_date.isoformat(),
                    meal_name,
                    st.session_state.last_result["calories"],
                    st.session_state.last_result["protein"]
                )
                st.session_state.last_result = None
                st.success("Meal saved successfully!")


# ======================================================
# TAB 2 — MULTIPLE ITEMS
# ======================================================

with tab2:
    st.subheader("🥗 Multi-Item Meal Calculator")

    st.markdown("### Ingredient Input")

    col1, col2 = st.columns(2)
    with col1:
        w = st.number_input("Weight (g)", min_value=0.0, key="mw")
        s = st.number_input("Serving Size (g)", min_value=1.0, key="ms")
    with col2:
        c = st.number_input("Calories per Serving", min_value=0.0, key="mc")
        p = st.number_input("Protein per Serving (g)", min_value=0.0, key="mp")

    if st.button("➕ Add Ingredient"):
        if w > 0:
            cal, pro = calculate_single_item(w, s, c, p)
            st.session_state.multi_items.append(
                {"calories": cal, "protein": pro}
            )
            st.success("Ingredient added")
        else:
            st.error("Weight must be greater than 0")

    if st.session_state.multi_items:
        st.markdown("### Current Ingredients")
        for i, item in enumerate(st.session_state.multi_items, 1):
            st.write(
                f"{i}. Calories: {item['calories']} | Protein: {item['protein']} g"
            )

    st.markdown("### Meal Details")
    col1, col2 = st.columns(2)
    with col1:
        meal_name = st.text_input("Meal Name", key="multi_meal_name")
    with col2:
        meal_date = st.date_input("Meal Date", value=date.today(), key="multi_meal_date")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Finish & Calculate", type="primary", key="calc_multi"):
            if not st.session_state.multi_items:
                st.error("Add at least one ingredient")
            else:
                cal, pro = calculate_multiple_items(
                    st.session_state.multi_items
                )
                st.session_state.last_result = {
                    "calories": cal,
                    "protein": pro
                }
                st.success(
                    f"Total Calories: {cal} kcal | Protein: {pro} g"
                )

    with col2:
        if st.button("Save Meal", type="primary", key="save_multi"):
            if st.session_state.last_result is None:
                st.error("Please calculate before saving.")
            else:
                insert_meal(
                    meal_date.isoformat(),
                    meal_name,
                    st.session_state.last_result["calories"],
                    st.session_state.last_result["protein"]
                )
                st.session_state.multi_items = []
                st.session_state.last_result = None
                st.success("Meal saved successfully!")


# ======================================================
# TAB 3 — DAILY SUMMARY
# ======================================================

with tab3:
    st.subheader("📅 Daily Meal Summary")

    selected_date = st.date_input(
        "Select Date", value=date.today(), key="view_date"
    )

    meals = get_meals_by_date(selected_date.isoformat())

    if meals:
        st.markdown("### Meals")
        for meal in meals:
            st.write(
                f"• **{meal[0]}** — {meal[1]} kcal | {meal[2]} g protein"
            )
    else:
        st.warning("No meals recorded for this date.")

    calories, protein = get_day_totals(selected_date.isoformat())

    st.markdown("### Daily Totals")
    col1, col2 = st.columns(2)
    col1.metric("Calories", calories)
    col2.metric("Protein (g)", protein)


# ======================================================
# TAB 4 — ANALYTICS
# ======================================================

with tab4:
    st.subheader("📊 Intake Analytics")

    summary = get_daily_summary()

    if summary:
        df = pd.DataFrame(
            summary, columns=["Date", "Calories", "Protein"]
        )
        df["Date"] = pd.to_datetime(df["Date"])

        col1, col2 = st.columns([3, 2])

        with col1:
            chart = alt.Chart(df).mark_line(point=True).encode(
                x="Date:T",
                y="Calories:Q",
                tooltip=["Date", "Calories"]
            ).properties(height=350)
            st.altair_chart(chart, use_container_width=True)

        with col2:
            st.markdown("### Average Intake")

            start = st.date_input(
                "Start Date", value=df["Date"].min().date(), key="analytics_start"
            )
            end = st.date_input(
                "End Date", value=df["Date"].max().date(), key="analytics_end"
            )

            avg_cal, avg_pro = get_average_between_dates(
                start.isoformat(), end.isoformat()
            )

            st.metric("Avg Calories", avg_cal)
            st.metric("Avg Protein (g)", avg_pro)
    else:
        st.info("No analytics available yet.")
>>>>>>> master
