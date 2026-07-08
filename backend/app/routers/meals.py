from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Meal as MealRow
from ..schemas import Meal, MealCreate

router = APIRouter(prefix="/api/meals", tags=["meals"])


@router.get("", response_model=list[Meal])
def list_meals(date: date_type | None = None, db: Session = Depends(get_db)):
    stmt = select(MealRow).order_by(MealRow.date, MealRow.id)
    if date is not None:
        stmt = stmt.where(MealRow.date == date)
    return db.scalars(stmt).all()


@router.post("", response_model=Meal, status_code=201)
def create_meal(meal: MealCreate, db: Session = Depends(get_db)):
    row = MealRow(
        date=meal.date,
        name=meal.name.strip(),
        calories=meal.calories,
        protein=meal.protein,
        carbs=meal.carbs,
        fat=meal.fat,
    )
    db.add(row)
    db.commit()
    return row


@router.delete("/{meal_id}", status_code=204)
def delete_meal(meal_id: int, db: Session = Depends(get_db)):
    row = db.get(MealRow, meal_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Meal not found")
    db.delete(row)
    db.commit()
