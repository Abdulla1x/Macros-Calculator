from fastapi import APIRouter, HTTPException, Query

from ..db import get_connection
from ..schemas import Food, FoodCreate, OFFProduct
from ..services import off_client

router = APIRouter(prefix="/api/foods", tags=["foods"])


@router.get("", response_model=list[Food])
def list_foods():
    conn = get_connection()
    try:
        rows = conn.execute("SELECT * FROM foods ORDER BY name").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.get("/search", response_model=list[Food])
def search_foods(q: str = Query(min_length=1)):
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT * FROM foods WHERE name LIKE ? COLLATE NOCASE
               ORDER BY CASE WHEN name LIKE ? COLLATE NOCASE THEN 0 ELSE 1 END, name
               LIMIT 10""",
            (f"%{q}%", f"{q}%"),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


@router.get("/lookup", response_model=list[OFFProduct])
async def lookup_openfoodfacts(q: str = Query(min_length=1)):
    try:
        return await off_client.search_products(q)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Open Food Facts lookup failed. Enter macros manually.",
        )


@router.post("", response_model=Food, status_code=201)
def save_food(food: FoodCreate):
    """Save a food to the local cache; updates macros if the name exists."""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO foods (name, serving_size, calories, protein, carbs, fat, source)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(name) DO UPDATE SET
                   serving_size = excluded.serving_size,
                   calories = excluded.calories,
                   protein = excluded.protein,
                   carbs = excluded.carbs,
                   fat = excluded.fat,
                   source = excluded.source""",
            (food.name.strip(), food.serving_size, food.calories,
             food.protein, food.carbs, food.fat, food.source),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM foods WHERE name = ? COLLATE NOCASE",
            (food.name.strip(),),
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


@router.delete("/{food_id}", status_code=204)
def delete_food(food_id: int):
    conn = get_connection()
    try:
        cur = conn.execute("DELETE FROM foods WHERE id = ?", (food_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Food not found")
    finally:
        conn.close()
