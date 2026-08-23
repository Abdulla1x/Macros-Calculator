"""Saved meals the user can re-log in one tap.

A template is a meal plus its ingredient rows. Meals themselves are flat -- the
rows someone types are discarded on save -- so this is the only place those
rows survive, which is what makes re-logging editable rather than all-or-
nothing.

No rate limiting here, per rate_limit.py's rule: only the auth endpoints are
limited, because everything else already requires a valid token.
"""
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import MealTemplate as MealTemplateRow
from ..models import User
from ..schemas import MealTemplate, MealTemplateCreate, TemplateItem
from ..upsert import upsert

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/meal-templates", tags=["meal-templates"])


def _items_of(row: MealTemplateRow) -> list[TemplateItem]:
    """Parse the stored ingredient rows, tolerating a column that can't be read.

    Nullable column, so absent items are normal and mean "totals only". A
    *malformed* value should not be fatal either: this list feeds the dashboard,
    and one unreadable row must not take the whole Quick log panel down with it.
    data.py carries the scar from the opposite choice -- json.loads("") raises,
    and it 500'd the entire export for anyone who had recorded a voice note.
    """
    if not row.items_json:
        return []
    try:
        # pydantic's ValidationError subclasses ValueError, so this covers both
        # "not JSON at all" and "JSON of the wrong shape".
        return [TemplateItem.model_validate(item) for item in json.loads(row.items_json)]
    except (ValueError, TypeError):
        logger.warning("meal_template %s has unreadable items_json", row.id)
        return []


def _template_out(row: MealTemplateRow, *, created: bool = False) -> MealTemplate:
    """Build the response model explicitly -- do not switch this to from_attributes.

    The ORM row has `items_json`, not `items`. Pydantic responds to a missing
    attribute on a defaulted field by substituting the default, silently, so
    from_attributes would return `items: []` for every template ever saved and
    nothing would raise. That is the Phase 2 `is_admin` bug exactly, and the fix
    is the same one: a single construction site that passes every field.
    """
    return MealTemplate(
        id=row.id,
        name=row.name,
        calories=row.calories,
        protein=row.protein,
        carbs=row.carbs,
        fat=row.fat,
        items=_items_of(row),
        created=created,
    )


@router.get("", response_model=list[MealTemplate])
def list_meal_templates(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Newest first.

    Not most-recently-used: that needs a `last_used_at` column, and ordering by
    it is a cross-dialect trap -- Postgres sorts NULLs first under DESC, SQLite
    sorts them last, so every never-used template would float to the top in
    production while the SQLite test suite showed it working. `id` breaks ties
    so two templates saved in the same second don't order arbitrarily.
    """
    stmt = (
        select(MealTemplateRow)
        .where(MealTemplateRow.user_id == user.id)
        .order_by(MealTemplateRow.created_at.desc(), MealTemplateRow.id.desc())
        .limit(limit)
    )
    return [_template_out(row) for row in db.scalars(stmt).all()]


@router.post("", response_model=MealTemplate, status_code=201)
def save_meal_template(
    body: MealTemplateCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save a template; replaces the one with this name if it already exists.

    Same upsert-by-lowercased-name shape as save_food, but with a consequence
    save_food does not have: a food is a name-to-macros mapping, so overwriting
    it is a correction, while a template is a name-to-ingredient-list and
    overwriting it destroys a composition. There is no undo, so the response
    says which of the two happened and the client words its message accordingly.
    """
    name = body.name.strip()
    created = False

    def build() -> MealTemplateRow:
        nonlocal created
        row = db.scalars(
            select(MealTemplateRow).where(
                MealTemplateRow.user_id == user.id,
                func.lower(MealTemplateRow.name) == name.lower(),
            )
        ).first()
        # Recomputed on every attempt, not captured once. If a concurrent save
        # created the row first, this call replaced a composition rather than
        # creating one, and the response has to say so -- the client words an
        # irreversible overwrite differently from a new save.
        created = row is None
        if row is None:
            row = MealTemplateRow(user_id=user.id, name=name)
            db.add(row)
        row.calories = body.calories
        row.protein = body.protein
        row.carbs = body.carbs
        row.fat = body.fat
        # NULL rather than "[]" when there are no items, so the column's
        # nullability keeps meaning "this template is totals only".
        row.items_json = (
            json.dumps([item.model_dump() for item in body.items])
            if body.items
            else None
        )
        return row

    row = upsert(db, build)
    return _template_out(row, created=created)


@router.delete("/{template_id}", status_code=204)
def delete_meal_template(
    template_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = db.scalars(
        select(MealTemplateRow).where(
            MealTemplateRow.id == template_id,
            MealTemplateRow.user_id == user.id,
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Meal template not found")
    db.delete(row)
    db.commit()
