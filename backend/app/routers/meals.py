from datetime import date as date_type

from fastapi import APIRouter, HTTPException

from ..db import get_connection
from ..schemas import Meal, MealCreate

router = APIRouter(prefix="/api/meals", tags=["meals"])


@router.get("", response_model=list[Meal])
def list_meals(date: date_type | None = None):
    conn = get_connection()
    try:
        if date is not None:
            rows = conn.execute(
                "SELECT * FROM meals WHERE date = ? ORDER BY id",
                (date.isoformat(),),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM meals ORDER BY date, id").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.post("", response_model=Meal, status_code=201)
def create_meal(meal: MealCreate):
    conn = get_connection()
    try:
        cur = conn.execute(
            """INSERT INTO meals (date, name, calories, protein, carbs, fat)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (meal.date.isoformat(), meal.name.strip(), meal.calories,
             meal.protein, meal.carbs, meal.fat),
        )
        conn.commit()
        return Meal(id=cur.lastrowid, **meal.model_dump())
    finally:
        conn.close()


@router.delete("/{meal_id}", status_code=204)
def delete_meal(meal_id: int):
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM meals WHERE id = ?", (meal_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Meal not found")
    finally:
        conn.close()
