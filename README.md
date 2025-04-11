# 🥗 Macros Calculator

A Python-based command-line application that helps users calculate, store, and analyze the calories and protein content of their meals. It supports both single ingredients and full meals, and now includes historical tracking, daily totals, and average intake analysis.

---

## 💡 Project Overview

Originally designed for calculating meal macros, this tool has evolved into a lightweight nutrition tracker. It now supports logging, reviewing, and analyzing nutritional data over time, helping users meet fitness or dietary goals.

---

## ✅ Features

- **🔹 Single & Multiple Item Support**  
  Calculate macros for individual ingredients or full meals.

- **🔹 Interactive CLI Menu**  
  Choose from options to calculate macros, view saved meals, check totals, or get averages.

- **🔹 Data Persistence**  
  Saves meals and daily summaries locally in JSON files (`Meal_Data.txt`, `total_intake_data.txt`).

- **🔹 Daily Intake Calculation**  
  View total calories and protein consumed per day.

- **🔹 Average Intake Over Time**  
  Enter a date range to calculate average calorie and protein intake.

- **🔹 Overwrite Protection**  
  Warns before overwriting previously saved data.

- **🔹 Error Handling**  
  Handles invalid input and edge cases like zero serving size.

---

## 🛠️ Technologies Used

- Python 3  
- JSON (for data storage)  
- File Handling  
- Exception Handling  
- `datetime` module for date comparison

---

## 📁 Example Use Case

1. Run the program.
2. Choose from menu:
   - Calculate macros
   - View stored meals
   - Check daily total intake
   - Calculate average intake over a date range
3. Input relevant data.
4. Save results if desired.
5. View and manage saved history.

---

## 📘 What I Learned

- Building a structured CLI menu system  
- Persistent storage using JSON  
- Parsing and comparing dates with `datetime`  
- Designing a functional, real-world nutrition tracker

---

## 📌 Future Improvements

- GUI version (Tkinter or PyQt)  
- Nutrition API integration  
- Track additional nutrients (carbs, fats, fiber)  
- Export data to CSV or graphs

---

## 📂 File Structure
- macros calculator.py     # Main script
- Meal_Data.txt            # Stores meals by date and name
- total_intake_data.txt    # Stores daily total calories/protein
