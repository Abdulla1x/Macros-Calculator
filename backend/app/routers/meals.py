from datetime import date as date_type

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import Meal as MealRow
from ..models import User, utcnow
from ..schemas import Meal, MealCreate

router = APIRouter(prefix="/api/meals", tags=["meals"])


@router.get("", response_model=list[Meal])
def list_meals(
    date: date_type | None = None,
    limit: int = Query(default=500, ge=1, le=1000),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    stmt = select(MealRow).where(MealRow.user_id == user.id)
    if date is not None:
        # A single day is naturally bounded; keep insertion order.
        stmt = stmt.where(MealRow.date == date).order_by(MealRow.date, MealRow.id)
    else:
        # Undated queries would otherwise return the whole history — cap them
        # at the most recent `limit` meals.
        stmt = stmt.order_by(MealRow.date.desc(), MealRow.id.desc()).limit(limit)
    return db.scalars(stmt).all()


# How many recent rows /api/meals/recent scans looking for distinct names.
#
# The endpoint returns one meal per name, so how far it must read to fill a list
# of `limit` depends entirely on how repetitive the account is: someone logging
# "Breakfast", "Lunch" and "Dinner" every day has three distinct names in any
# number of rows, and no window would find a fourth. A list shorter than `limit`
# is the honest answer there, not a shortfall.
#
# 200 is about fifty days for a four-meal-a-day account -- far enough back that
# anything older is not a meal you are about to log again, and bounded, which is
# the point of having a number here at all.
RECENT_SCAN_ROWS = 200


def _distinct_by_name(rows: list[MealRow], limit: int) -> list[MealRow]:
    """The first row for each distinct name, in the order given, up to `limit`.

    Case-insensitive, matching the convention `foods` and `meal_templates`
    already enforce with their expression indexes: "Breakfast" and "breakfast"
    are one meal to a person, and offering both would be this list failing at
    the one job it has.

    Callers pass rows newest-first, so the row kept for a name is the most
    recent one. Two meals can share a name and hold different macros -- Monday's
    breakfast was not Tuesday's -- and the newest is the better guess at what
    "log it again" means. It is still a guess, which is why the row carries its
    date into the UI instead of presenting its numbers as the name's.
    """
    seen: set[str] = set()
    kept: list[MealRow] = []
    for row in rows:
        key = row.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
        if len(kept) == limit:
            break
    return kept


@router.get("/recent", response_model=list[Meal])
def recent_meals(
    limit: int = Query(default=8, ge=1, le=50),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The most recent meal under each distinct name -- "log it again".

    Saved meals cover the meal you thought to store in advance; this covers the
    one you ate on Tuesday and did not think to save. Deduplicated because an
    account that logs "Breakfast" every day would otherwise be offered the same
    name six times.

    Ordered like the undated branch of `list_meals` above, so the two agree
    about what "recent" means rather than each having its own idea.

    Deduplicated in Python rather than with DISTINCT ON, which is Postgres-only
    while the suite runs SQLite -- a rule that holds on one dialect is a rule
    the tests cannot defend. Same trap `lib/recentTemplates.ts` documents about
    NULL ordering, from the other direction.

    ⚠️ Declared ABOVE the `/{meal_id}` routes. Nothing routes GET on a path
    parameter today, so "recent" cannot be read as an id -- but adding
    `GET /{meal_id}` later would shadow this one unless it stays underneath.
    """
    stmt = (
        select(MealRow)
        .where(MealRow.user_id == user.id)
        .order_by(MealRow.date.desc(), MealRow.id.desc())
        .limit(RECENT_SCAN_ROWS)
    )
    return _distinct_by_name(list(db.scalars(stmt).all()), limit)


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
    # Stamped unconditionally rather than only when a field actually differs:
    # a PUT that resubmits identical values is still the user having gone back
    # and confirmed the row, and "was this touched" is the question the column
    # is here to answer. `created_at` is never rewritten -- a correction does
    # not change when the meal was first logged.
    row.updated_at = utcnow()
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
