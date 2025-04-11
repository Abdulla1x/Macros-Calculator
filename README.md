# 🥗 Macros Calculator

A Python-based command-line application that helps users calculate and store the calories and protein content of their meals. Whether it's a single ingredient or a complete meal made of multiple ingredients, this tool ensures easy nutrition tracking with persistent data storage.

---

## 💡 Project Overview

This project simplifies the process of tracking nutritional information for meals, especially for those with fitness or health-related goals. The app guides users through entering data and supports saving and retrieving historical records.

---

## ✅ Features

- **🔹 Single & Multiple Item Support**  
  Calculate macros for a single ingredient or full meals.

- **🔹 Interactive Input with Error Handling**  
  User-friendly prompts with checks for invalid input and division by zero.

- **🔹 Calorie & Protein Calculation**  
  Computes total calories and protein based on weight and serving size.

- **🔹 Data Persistence**  
  Saves meals by name and date in `Meal_Data.txt` using JSON format.

- **🔹 Readable Output**  
  Displays macros per item and total meal macros clearly.

---

## 🛠️ Technologies Used

- Python 3  
- JSON (for saving meal history)  
- File Handling (read/write operations)  
- Exception Handling (robust input checks)

---

## 📁 Example Use Case

1. Choose single or multiple ingredient input.  
2. Enter weight, serving size, and macros per serving.  
3. Instantly view calculated calories and protein.  
4. Optionally save the meal with a custom name and date.  
5. Data is stored locally and persistently.

---

## 🧠 What I Learned

- Structuring a CLI app.  
- Using `json` for data storage.  
- Graceful error handling with `try-except`.  
- Building a practical nutrition-tracking utility.

---

## 📌 Future Improvements

- GUI version (Tkinter or PyQt)  
- Retrieve/view saved meal history  
- Add support for carbs and fats  
- Integrate with nutrition APIs

---

## 📂 File Structure
- macros calculator.py     # Main application script
- Meal_Data.txt            # JSON file storing saved meals
