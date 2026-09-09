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


def _distinct_by_name(
    rows: list[MealRow], limit: int, demoted: frozenset[str] = frozenset()
) -> list[MealRow]:
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

    `demoted` names sort to the END rather than being dropped. The card exists
    to offer what you have not got round to logging, and an account that has
    already logged six meals today has six of the newest distinct names -- so
    without this the list is six things sitting in full further down the same
    page. Demotion rather than exclusion because people do eat the same thing
    twice in a day: dropping "Tea" because you had one this morning would break
    the card for its second-best case.

    ⚠️ The demotion has to happen BEFORE the cap, which is why it lives here and
    not in the caller. Deduplication truncates at `limit`, so by the time a
    client sees the list the names worth promoting have already been cut from
    it -- a reordering done downstream has nothing left to reorder. Found in a
    browser, after exactly that was tried.
    """
    seen: set[str] = set()
    kept: list[MealRow] = []
    held: list[MealRow] = []
    for row in rows:
        key = row.name.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        (held if key in demoted else kept).append(row)
        # Once `limit` names survive undemoted, nothing held back can reach the
        # result, so the remaining scan cannot change the answer.
        if len(kept) == limit:
            break
    return (kept + held)[:limit]


@router.get("/recent", response_model=list[Meal])
def recent_meals(
    limit: int = Query(default=8, ge=1, le=50),
    demote_date: date_type | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The most recent meal under each distinct name -- "recently logged".

    Saved meals cover the meal you thought to store in advance; this covers the
    one you ate on Tuesday and did not think to save. Deduplicated because an
    account that logs "Breakfast" every day would otherwise be offered the same
    name six times.

    Ordered like the undated branch of `list_meals` above, so the two agree
    about what "recent" means rather than each having its own idea.

    `demote_date` is the day the caller is showing. Names already logged on it
    sort last -- see `_distinct_by_name`. Optional, and absent means "do not
    reorder", so a client that has never heard of it gets exactly what it got
    before.

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
    rows = list(db.scalars(stmt).all())
    # Read off the rows already scanned rather than asking again: the window is
    # newest-first, so any meal on `demote_date` is inside it whenever there is
    # anything newer to compare against.
    demoted = frozenset(
        row.name.strip().lower() for row in rows if row.date == demote_date
    ) if demote_date is not None else frozenset()
    return _distinct_by_name(rows, limit, demoted)


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
