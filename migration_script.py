import json
import sqlite3
from datetime import datetime

DB_NAME = "macros.db"
MEAL_FILE = "Meal_Data.txt"


def get_connection():
    return sqlite3.connect(DB_NAME)


def migrate_meals():
    # Load JSON
    with open(MEAL_FILE, "r") as f:
        meal_data = json.load(f)

    conn = get_connection()
    cur = conn.cursor()

    inserted = 0

    for date_str, meals in meal_data.items():
        # Convert DD-MM-YYYY → YYYY-MM-DD
        try:
            date_obj = datetime.strptime(date_str, "%d-%m-%Y")
            sql_date = date_obj.strftime("%Y-%m-%d")
        except ValueError:
            # Skip malformed dates
            print(f"Skipping invalid date: {date_str}")
            continue

        for meal_name, values in meals.items():
            calories, protein = values

            cur.execute(
                """
                INSERT INTO meals (date, name, calories, protein)
                VALUES (?, ?, ?, ?)
                """,
                (sql_date, meal_name.strip(), calories, protein)
            )
            inserted += 1

    conn.commit()
    conn.close()

    print(f"✅ Migration complete. Inserted {inserted} meals.")


if __name__ == "__main__":
    migrate_meals()
