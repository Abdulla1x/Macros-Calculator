from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import Food as FoodRow
from ..models import User
from ..schemas import Food, FoodCreate, OFFProduct
from ..services import off_client
from ..upsert import upsert

router = APIRouter(prefix="/api/foods", tags=["foods"])


@router.get("", response_model=list[Food])
def list_foods(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.scalars(
        select(FoodRow).where(FoodRow.user_id == user.id).order_by(FoodRow.name)
    ).all()


def _escape_like(value: str) -> str:
    """Make % and _ in a search query match themselves.

    LIKE reads % as "any run of characters" and _ as "any one character", so
    without this, searching "100%" matches every food in the library and
    searching "_" matches all of them too. Not a security problem -- the query
    is still a bound parameter, and every row is user_id-scoped -- but a
    wrong-results one.

    Backslash first, or the two escapes added after it get escaped in turn.
    """
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("/search", response_model=list[Food])
def search_foods(
    q: str = Query(min_length=1),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Both patterns are escaped, not just the filter: prefix_first decides which
    # match sorts to the top, so if the two disagreed about what the query means
    # the ranking would promote a row the filter never selected.
    pattern = _escape_like(q)
    prefix_first = case((FoodRow.name.ilike(f"{pattern}%", escape="\\"), 0), else_=1)
    stmt = (
        select(FoodRow)
        .where(
            FoodRow.user_id == user.id,
            FoodRow.name.ilike(f"%{pattern}%", escape="\\"),
        )
        .order_by(prefix_first, FoodRow.name)
        .limit(10)
    )
    return db.scalars(stmt).all()


@router.get("/lookup", response_model=list[OFFProduct])
async def lookup_openfoodfacts(
    q: str = Query(min_length=1),
    user: User = Depends(get_current_user),
):
    # No user data involved, but auth is still required: this proxies an
    # external service and shouldn't be an anonymous relay.
    try:
        return await off_client.search_products(q)
    except Exception:
        raise HTTPException(
            status_code=502,
            detail="Open Food Facts lookup failed. Enter macros manually.",
        )


@router.post("", response_model=Food, status_code=201)
def save_food(
    food: FoodCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a food to the user's library; updates macros if the name exists."""
    name = food.name.strip()

    def build() -> FoodRow:
        row = db.scalars(
            select(FoodRow).where(
                FoodRow.user_id == user.id,
                func.lower(FoodRow.name) == name.lower(),
            )
        ).first()
        if row is None:
            row = FoodRow(user_id=user.id, name=name)
            db.add(row)
        row.serving_size = food.serving_size
        row.calories = food.calories
        row.protein = food.protein
        row.carbs = food.carbs
        row.fat = food.fat
        row.source = food.source
        return row

    return upsert(db, build)


def _owned(db: Session, user_id: int, food_id: int) -> FoodRow:
    """The caller's food, or 404.

    Both endpoints that take a `food_id` from the client go through this.
    Scoping on user_id here is what makes a guessed id a 404 rather than an
    edit to another account's library -- the same rule supplements.py states
    for the same reason.
    """
    row = db.scalars(
        select(FoodRow).where(FoodRow.id == food_id, FoodRow.user_id == user_id)
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Food not found")
    return row


@router.put("/{food_id}", response_model=Food)
def update_food(
    food_id: int,
    food: FoodCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Edit one food in place: rename it, correct its macros, or both.

    A full replace by id, where POST above is an upsert by name. That asymmetry
    is not an inconsistency, and it is forced by who calls what. POST's two
    callers -- FoodAutocomplete caching an Open Food Facts pick, and LogMeal's
    "save to library" checkbox -- hold a *name* and cannot know whether the row
    already exists. The Settings editor always holds the row in full, id
    included. It is the same split supplements.py draws between saving a
    template and adding a supplement.

    Renaming is why this endpoint exists at all: POST with a changed name
    matches nothing and creates a *second* row, so before this there was no way
    to correct a name -- only to accumulate the mistake.

    `source` is decided here rather than taken from the body. A row that came
    from Open Food Facts and has had a number corrected is no longer what Open
    Food Facts said, and leaving the badge on it would claim a provenance the
    numbers no longer have -- in the one section of the app whose whole job is
    telling the user which figures to trust. A rename changes no number, so it
    keeps the badge.

    Not app.upsert.upsert(). That helper is for upserts by natural key, where
    the loser of a race should re-read and apply its update on top. Renaming
    onto a name another row already holds is not a race -- it is a genuine
    conflict, and folding the two rows together would delete one the user never
    asked to lose. So it answers 409, exactly as supplements.py does.
    """
    row = _owned(db, user.id, food_id)
    name = food.name.strip()

    # Read before assigning: once the fields are written the previous values are
    # gone and there is nothing left to compare against.
    #
    # Exact float comparison, deliberately. The question is "did the client send
    # a different number", not "are these two close" -- the stored value came
    # from an earlier JSON payload, so an unchanged field round-trips to the
    # identical float and a tolerance would only let a real edit through as a
    # non-edit.
    numbers_changed = (
        row.serving_size != food.serving_size
        or row.calories != food.calories
        or row.protein != food.protein
        or row.carbs != food.carbs
        or row.fat != food.fat
    )

    row.name = name
    row.serving_size = food.serving_size
    row.calories = food.calories
    row.protein = food.protein
    row.carbs = food.carbs
    row.fat = food.fat
    if numbers_changed:
        row.source = "user"

    try:
        db.commit()
    except IntegrityError:
        # The expression index uq_foods_user_lower_name, not a pre-flight
        # SELECT: a check-then-insert has a race a unique constraint does not.
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f'You already have a food called "{name}".',
        )
    return row


@router.delete("/{food_id}", status_code=204)
def delete_food(
    food_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove one food from the library.

    Meals already logged are untouched: a Meal is a flat row carrying its own
    macros, with no foreign key to foods, so deleting one here changes what
    autocomplete offers next time and nothing about recorded history.
    """
    db.delete(_owned(db, user.id, food_id))
    db.commit()
