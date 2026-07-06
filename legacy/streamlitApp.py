import streamlit as st
import pandas as pd
import altair as alt
from datetime import date
import time

from macros_calculator import (
    init_db,
    calculate_single_item,
    calculate_multiple_items,
    insert_meal,
    get_meals_by_date,
    get_day_totals,
    get_daily_summary,
    get_average_between_dates,
    delete_meal
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
            if not meal_name.strip():
                st.error("Please enter a meal name before saving.")
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
            elif not meal_name.strip():
                st.error("Please enter a meal name before saving.")
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
            meal_id, name, calories, protein = meal

            col1, col2 = st.columns([4,1])

            with col1:
                st.write(f"**{name}** — {calories} kcal | {protein} g protein")

            with col2:
                confirm_key = f"confirm_delete_{meal_id}"

                # If user clicked delete, ask for confirmation
                if st.button("Delete", key=f"delete_{meal_id}"):
                    st.session_state[confirm_key] = True

                # Show confirmation buttons only if delete was clicked
                if st.session_state.get(confirm_key):
                    st.warning("Are you sure you want to delete this meal?")
                    confirm_col, cancel_col = st.columns(2)

                    with confirm_col:
                        if st.button("Yes", key=f"yes_{meal_id}"):
                            delete_meal(meal_id)
                            st.success("Meal deleted!")
                            time.sleep(1.5)  # Brief pause before hiding confirmation
                            st.session_state[confirm_key] = False
                            st.rerun()

                    with cancel_col:
                        if st.button("No", key=f"no_{meal_id}"):
                            st.session_state[confirm_key] = False
                            st.info("Deletion cancelled.")
                            time.sleep(1.5)  # Brief pause before hiding confirmation
                            st.rerun()

        calories, protein = get_day_totals(selected_date.isoformat())
        
        st.markdown("### Daily Totals")
        col1, col2 = st.columns(2)
        col1.metric("Calories", calories)
        col2.metric("Protein (g)", protein)

    else:
        st.write("No meals recorded for this date.")


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

        # ======================================================
        # CLEAN & VALIDATE DATES
        # ======================================================

        df["Date"] = pd.to_datetime(
            df["Date"],
            format="mixed",
            errors="coerce"
        )

        invalid_rows = df[df["Date"].isna()]

        if not invalid_rows.empty:
            st.warning(f"⚠️ Found {len(invalid_rows)} invalid date entries.")

            st.markdown("### ⚠️ Invalid Rows (Need Fixing)")
            st.dataframe(invalid_rows)

            invalid_csv = invalid_rows.to_csv(index=False).encode("utf-8")

            st.download_button(
                label="⬇️ Download Invalid Rows",
                data=invalid_csv,
                file_name="invalid_rows_fix.csv",
                mime="text/csv"
            )

            st.info("💡 Fix the 'date' column (YYYY-MM-DD) and re-upload.")

        df = df.dropna(subset=["Date"])

        if df.empty:
            st.warning("No valid data available after cleaning.")
            st.stop()

        df = df.sort_values("Date")

        # ======================================================
        # DATE RANGE FILTER
        # ======================================================

        col_filter1, col_filter2 = st.columns(2)

        with col_filter1:
            start = st.date_input(
                "Start Date",
                value=df["Date"].min().date(),
                key="analytics_start"
            )

        with col_filter2:
            end = st.date_input(
                "End Date",
                value=df["Date"].max().date(),
                key="analytics_end"
            )

        filtered_df = df[
            (df["Date"] >= pd.to_datetime(start)) &
            (df["Date"] <= pd.to_datetime(end))
        ]

        if filtered_df.empty:
            st.warning("No data available for selected date range.")
            st.stop()

        # ======================================================
        # SUMMARY METRICS
        # ======================================================

        colA, colB, colC, colD = st.columns(4)

        colA.metric("Total Calories", int(filtered_df["Calories"].sum()))
        colB.metric("Total Protein (g)", round(filtered_df["Protein"].sum(), 1))

        avg_cal, avg_pro = get_average_between_dates(
            start.isoformat(), end.isoformat()
        )

        colC.metric("Avg Calories", avg_cal)
        colD.metric("Avg Protein (g)", avg_pro)

        # ======================================================
        # SEPARATE CHARTS FOR CALORIES AND PROTEIN
        # ======================================================

        st.markdown("### 📊 Calorie Intake Over Time")
        calorie_chart = alt.Chart(filtered_df).mark_line(point=True).encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Calories:Q", title="Calories"),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Calories:Q", title="Calories")
            ]
        ).properties(height=350)
        st.altair_chart(calorie_chart, use_container_width=True)

        st.markdown("### 📊 Protein Intake Over Time")
        protein_chart = alt.Chart(filtered_df).mark_line(point=True).encode(
            x=alt.X("Date:T", title="Date"),
            y=alt.Y("Protein:Q", title="Protein (g)"),
            tooltip=[
                alt.Tooltip("Date:T", title="Date"),
                alt.Tooltip("Protein:Q", title="Protein (g)")
            ]
        ).properties(height=350)
        st.altair_chart(protein_chart, use_container_width=True)

        # ======================================================
        # TABLE VIEW
        # ======================================================

        st.markdown("### 📋 Daily Intake Table")
        st.dataframe(
            filtered_df.style.format({
                "Calories": "{:.0f}",
                "Protein": "{:.1f}"
            }),
            use_container_width=True
        )

    else:
        st.info("No analytics available yet.")

    # ======================================================
    # EXPORT DATA
    # ======================================================

    import sqlite3

    st.markdown("### 📥 Export Data")

    conn = sqlite3.connect("macros.db")
    df_export = pd.read_sql_query("SELECT * FROM meals", conn)
    conn.close()

    if not df_export.empty:
        csv_data = df_export.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="Download Full Backup",
            data=csv_data,
            file_name="macros_full_backup.csv",
            mime="text/csv"
        )
    else:
        st.warning("No data available to export.")

    # ======================================================
    # IMPORT DATA
    # ======================================================

    st.markdown("### 📤 Import Data")

    uploaded_file = st.file_uploader("Upload CSV", type=["csv"])

    if uploaded_file is not None:
        df_import = pd.read_csv(uploaded_file)

        st.write("Preview of uploaded data:")
        st.dataframe(df_import)

        df_import.columns = [col.lower() for col in df_import.columns]

        if "date" in df_import.columns:
            df_import["date"] = pd.to_datetime(
                df_import["date"],
                format="mixed",
                errors="coerce"
            )

            invalid_dates = df_import["date"].isna().sum()
            if invalid_dates > 0:
                st.warning(f"{invalid_dates} rows had invalid dates and were removed.")

            df_import = df_import.dropna(subset=["date"])
            df_import["date"] = df_import["date"].dt.strftime("%Y-%m-%d")

        required_columns = {"date", "name", "calories", "protein"}

        if not required_columns.issubset(set(df_import.columns)):
            st.error("Invalid CSV format. Required columns: date, name, calories, protein")
        else:
            if st.button("Import Data"):
                conn = sqlite3.connect("macros.db")
                cur = conn.cursor()

                inserted = 0
                skipped = 0
                progress_bar = st.progress(0)

                total_rows = len(df_import)

                for i, row in df_import.iterrows():
                    date = row["date"]
                    name = row["name"]
                    calories = row["calories"]
                    protein = row["protein"]

                    cur.execute("""
                        SELECT COUNT(*) FROM meals
                        WHERE date=? AND name=? AND calories=? AND protein=?
                    """, (date, name, calories, protein))

                    exists = cur.fetchone()[0]

                    if not exists:
                        cur.execute("""
                            INSERT INTO meals (date, name, calories, protein)
                            VALUES (?, ?, ?, ?)
                        """, (date, name, calories, protein))
                        inserted += 1
                    else:
                        skipped += 1

                    progress_bar.progress((i + 1) / total_rows)

                conn.commit()
                conn.close()

                st.success(f"Imported {inserted} meals, skipped {skipped} duplicates.")
                st.rerun()