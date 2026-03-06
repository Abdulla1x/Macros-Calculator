import sqlite3
from typing import List, Dict, Tuple

DB_NAME = "macros.db"


# =========================
# DATABASE SETUP
# =========================

def get_connection():
    return sqlite3.connect(DB_NAME)


def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            name TEXT NOT NULL,
            calories REAL NOT NULL,
            protein REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()


# =========================
# CALCULATION LOGIC
# =========================

def calculate_single_item(
    weight: float,
    serving_size: float,
    calories_per_serving: float,
    protein_per_serving: float
) -> Tuple[float, float]:

    if serving_size <= 0:
        raise ValueError("Serving size must be greater than zero")

    calories = (weight / serving_size) * calories_per_serving
    protein = (weight / serving_size) * protein_per_serving

    return round(calories, 2), round(protein, 2)


def calculate_multiple_items(items: List[Dict]) -> Tuple[float, float]:
    total_calories = sum(item["calories"] for item in items)
    total_protein = sum(item["protein"] for item in items)

    return round(total_calories, 2), round(total_protein, 2)


# =========================
# DATABASE OPERATIONS
# =========================

def insert_meal(date: str, name: str, calories: float, protein: float):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO meals (date, name, calories, protein) VALUES (?, ?, ?, ?)",
        (date, name, calories, protein)
    )
    conn.commit()
    conn.close()


def get_meals_by_date(date: str) -> List[Tuple]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, name, calories, protein FROM meals WHERE date = ?",
        (date,)
    )
    results = cur.fetchall()
    conn.close()
    return results


def get_day_totals(date: str) -> Tuple[float, float]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT SUM(calories), SUM(protein) FROM meals WHERE date = ?",
        (date,)
    )
    calories, protein = cur.fetchone()
    conn.close()

    return round(calories or 0, 2), round(protein or 0, 2)


def get_daily_summary() -> List[Tuple]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT date, SUM(calories), SUM(protein)
        FROM meals
        GROUP BY date
        ORDER BY date
    """)
    results = cur.fetchall()
    conn.close()
    return results


def get_average_between_dates(start_date: str, end_date: str) -> Tuple[float, float]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT AVG(daily_calories), AVG(daily_protein)
        FROM (
            SELECT date,
                   SUM(calories) AS daily_calories,
                   SUM(protein) AS daily_protein
            FROM meals
            WHERE date BETWEEN ? AND ?
            GROUP BY date
        )
    """, (start_date, end_date))

    avg_cal, avg_pro = cur.fetchone()
    conn.close()

    return round(avg_cal or 0, 2), round(avg_pro or 0, 2)


def delete_meal(meal_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(                            
        "DELETE FROM meals WHERE id = ?", 
        (meal_id,)
    )
    conn.commit()
    conn.close()