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