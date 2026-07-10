from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import Meal as MealRow
from ..models import User
from ..schemas import Meal, MealCreate

router = APIRouter(prefix="/api/meals", tags=["meals"])


@router.get("", response_model=list[Meal])
def list_meals(
    date: date_type | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(MealRow)
        .where(MealRow.user_id == user.id)
        .order_by(MealRow.date, MealRow.id)
    )
    if date is not None:
        stmt = stmt.where(MealRow.date == date)
    return db.scalars(stmt).all()


@router.post("", response_model=Meal, status_code=201)
def create_meal(
    meal: MealCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = MealRow(
        user_id=user.id,
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


@router.put("/{meal_id}", response_model=Meal)
def update_meal(
    meal_id: int,
    meal: MealCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.scalars(
        select(MealRow).where(MealRow.id == meal_id, MealRow.user_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Meal not found")
    row.date = meal.date
    row.name = meal.name.strip()
    row.calories = meal.calories
    row.protein = meal.protein
    row.carbs = meal.carbs
    row.fat = meal.fat
    db.commit()
    return row


@router.delete("/{meal_id}", status_code=204)
def delete_meal(
    meal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.scalars(
        select(MealRow).where(MealRow.id == meal_id, MealRow.user_id == user.id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Meal not found")
    db.delete(row)
    db.commit()
