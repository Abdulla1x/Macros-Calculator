from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..duplicates import LibraryFood, find_duplicates
from ..models import Food as FoodRow
from ..models import User
from ..schemas import Food, FoodCreate, FoodDuplicatePair, OFFProduct
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


@router.get("/duplicates", response_model=list[FoodDuplicatePair])
def list_duplicates(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Pairs of saved foods that look like the same thing twice.

    A literal path, declared above the `/{food_id}` routes below. Nothing would
    actually collide today -- there is no GET by id -- but the ordering is what
    keeps that true if one is ever added, and FastAPI resolves in declaration
    order.

    The judgement lives in app/duplicates.py, on plain values, so its thresholds
    are testable without a database. This end does one thing the pure module
    cannot: scope the rows to the caller. A duplicate is a fact about one
    person's library, and there is no query here that could see anyone else's.
    """
    rows = db.scalars(
        select(FoodRow).where(FoodRow.user_id == user.id).order_by(FoodRow.id)
    ).all()
    pairs = find_duplicates(
        [
            LibraryFood(row.id, row.name, row.serving_size, row.calories, row.protein)
            for row in rows
        ]
    )
    return [FoodDuplicatePair(a_id=pair.a_id, b_id=pair.b_id) for pair in pairs]


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


# What "normalised" means here. 100 g is what Open Food Facts reports against,
# what the library's add form already defaults to, and what
# lib/libraryMatch.ts::foodFromAnalyzedItem converts a saved AI estimate to --
# so this is the fourth place that agrees on it rather than a new convention.
NORMALIZED_SERVING_G = 100


@router.post("/{food_id}/normalize", response_model=Food)
def normalize_food(
    food_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rescale one food so its macros are per 100 g, changing nothing else.

    **Why this is an endpoint and not a PUT from the client.** update_food above
    flips `source` to 'user' the moment any number differs, and that rule is
    right: a corrected row is no longer what Open Food Facts said. But a rescale
    is not a correction. 108 kcal per 90 g and 120 kcal per 100 g are the same
    claim in different units, and routing this through PUT would strip the
    provenance badge off every third-party row a user tidies -- in the one
    screen whose entire job is telling them which figures to trust.

    The alternative was to teach PUT to *infer* a rescale by checking whether
    every macro moved by the same factor as the serving size. That needs a float
    tolerance, against an exact-comparison rule update_food documents at length
    and depends on; and it would still be a guess about intent. An endpoint does
    not guess. The request itself is the intent, which is why `source` is simply
    not assigned below rather than being carefully preserved.

    Idempotent: a row already at 100 g is returned untouched with a 200. The
    client would otherwise need a special case for the button it has already
    hidden, and "nothing to do" is not an error.
    """
    row = _owned(db, user.id, food_id)
    if row.serving_size == NORMALIZED_SERVING_G:
        return row

    factor = NORMALIZED_SERVING_G / row.serving_size

    # One decimal, for the reason libraryMatch.ts::foodFromAnalyzedItem gives
    # for the same rounding: the result is read by a person in a form they can
    # edit, and handing them 120.00000000000001 invites them to "fix" a number
    # that was never wrong.
    def scaled(value: float) -> float:
        return round(value * factor, 1)

    def scaled_or_none(value: float | None) -> float | None:
        # carbs and fat are the nullable pair, and None means "not recorded",
        # which is not zero. A missing macro stays missing rather than being
        # scaled into a claim the row never made.
        return None if value is None else scaled(value)

    row.serving_size = float(NORMALIZED_SERVING_G)
    row.calories = scaled(row.calories)
    row.protein = scaled(row.protein)
    row.carbs = scaled_or_none(row.carbs)
    row.fat = scaled_or_none(row.fat)
    # `source` is deliberately not touched. See the docstring.
    db.commit()
    return row
