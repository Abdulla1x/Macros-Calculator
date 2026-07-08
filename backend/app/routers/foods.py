from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Food as FoodRow
from ..schemas import Food, FoodCreate, OFFProduct
from ..services import off_client

router = APIRouter(prefix="/api/foods", tags=["foods"])


@router.get("", response_model=list[Food])
def list_foods(db: Session = Depends(get_db)):
    return db.scalars(select(FoodRow).order_by(FoodRow.name)).all()


@router.get("/search", response_model=list[Food])
def search_foods(q: str = Query(min_length=1), db: Session = Depends(get_db)):
    prefix_first = case((FoodRow.name.ilike(f"{q}%"), 0), else_=1)
    stmt = (
        select(FoodRow)
        .where(FoodRow.name.ilike(f"%{q}%"))
        .order_by(prefix_first, FoodRow.name)
        .limit(10)
    )
    return db.scalars(stmt).all()


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
def save_food(food: FoodCreate, db: Session = Depends(get_db)):
    """Save a food to the local cache; updates macros if the name exists."""
    name = food.name.strip()
    row = db.scalars(
        select(FoodRow).where(func.lower(FoodRow.name) == name.lower())
    ).first()
    if row is None:
        row = FoodRow(name=name)
        db.add(row)
    row.serving_size = food.serving_size
    row.calories = food.calories
    row.protein = food.protein
    row.carbs = food.carbs
    row.fat = food.fat
    row.source = food.source
    db.commit()
    return row


@router.delete("/{food_id}", status_code=204)
def delete_food(food_id: int, db: Session = Depends(get_db)):
    row = db.get(FoodRow, food_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Food not found")
    db.delete(row)
    db.commit()
