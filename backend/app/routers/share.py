"""Meal share codes: turn one of your meals into a string, and read one back.

A code is the meal itself, not a link to it. Nothing is stored, so there is no
table here, nothing to expire and nothing to revoke -- see app/share.py for the
format and for why it carries no signature.

**This router owns no rows, and that is the whole design.** Encoding reads one
row the caller already owns; decoding reads a string and writes nothing at all.
The recipient ends up with a meal because their own client POSTs to /api/meals
like any other save. That is what keeps the cross-tenant guarantee absolute
rather than conditional: there is no path here by which one account reads
another's data, so test_isolation.py gains cases rather than exceptions.

One router for the feature rather than a /share verb hung off /api/meals and
/api/meal-templates, following plan.py -- which reads meals and settings while
owning /api/plan, because the feature is the unit, not the table. Two encoders
in two files could also drift apart, and one construction site for a payload is
the lesson _template_out already records. A code is not a sub-resource in any
case: it is not addressable, not stored and not retrievable later, so
GET /api/meals/{id}/share would promise a thing that lives at a URL when
nothing does.

No rate limiting, per rate_limit.py's rule that only the auth endpoints are
limited because everything else already requires a valid token -- and decode is
worth checking against that rule rather than waving through, since it is the one
endpoint here whose job is to eat a long string a stranger wrote. It holds: a
caller must be signed in, each call costs at most a bounded 64 KiB, it spends no
third-party quota and it guards no secret. The byte caps in app/share.py are the
real control, and unlike an in-memory per-IP counter they do not reset on every
deploy.

⚠️ Known and NOT fixed here: Starlette reads a request body in full before
pydantic's max_length can refuse it, so a huge POST is allocated before
ShareDecodeRequest ever sees it. That is true of every POST in this app today
and predates this file. It is noted here because this is the first endpoint
whose *purpose* is to accept an arbitrarily long attacker-supplied string, which
makes it the natural trigger for a body-size middleware if one is ever written.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import Meal as MealRow
from ..models import MealTemplate as MealTemplateRow
from ..models import User
from ..schemas import ShareCode, ShareDecodeRequest, SharedMeal
from ..share import ShareCodeError, decode_share_code, encode_share_code
from .meal_templates import _items_of

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/share", tags=["share"])

# One sentence, not the pydantic field path. `items.0.calories` describes the
# *sender's* payload internals, which the person pasting the code did not write
# and cannot fix; their only move is to ask for a new code. The field path goes
# to the log instead, following _items_of's warn-rather-than-raise posture.
_SHAPE_REFUSAL = "That code isn't a meal this app can read. Ask for a new one."

# A legacy row can hold a value that would not be accepted today -- meals
# predate allow_inf_nan=False. Refusing one explicit share of one row with a
# sentence is honest; calibration.py warns against re-validating stored rows
# because there the same strictness would have silently dropped rows out of an
# aggregate. One row and one button is the case where refusing is right.
_CANNOT_SHARE = "This meal has a value that can't be shared."


def _code_for(payload: dict) -> ShareCode:
    """Validate a row's numbers, then encode them.

    Validated on the way *out* as well as the way in, so a code this app mints
    can never say something the app would refuse to read back.

    Validating first also makes SharedMeal an **allowlist** for the payload:
    pydantic drops fields the model does not declare, so a key added to the dict
    above -- a row id, a user id, a date -- cannot reach the encoded code at all.
    Verified by adding `id` to the dict and watching the payload stay six keys
    wide. Anything that does leak has to be added to SharedMeal itself, which is
    where the test looking for it points.
    """
    try:
        shared = SharedMeal.model_validate(payload)
    except ValidationError:
        logger.warning("refusing to share a row that fails SharedMeal validation")
        raise HTTPException(status_code=422, detail=_CANNOT_SHARE) from None
    try:
        # exclude_none so an untracked macro travels as an absent key rather
        # than a null. The decoder's defaults restore it to None either way, and
        # it is a few characters off every code.
        code = encode_share_code(shared.model_dump(exclude_none=True))
    except ShareCodeError:
        logger.warning("refusing to share a row the codec could not encode")
        raise HTTPException(status_code=422, detail=_CANNOT_SHARE) from None
    return ShareCode(code=code)


@router.get("/meal/{meal_id}", response_model=ShareCode)
def share_meal(
    meal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Encode a logged meal. GET because it creates nothing and repeats safely."""
    row = db.scalar(
        select(MealRow).where(MealRow.id == meal_id, MealRow.user_id == user.id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Meal not found")
    # items is empty because a Meal *is* empty of them: the rows someone typed
    # are discarded on save (models.py). The recipient's form falls back to a
    # single totals row, which is the same thing it already does for a template
    # saved while editing a meal.
    return _code_for(
        {
            "name": row.name,
            "calories": row.calories,
            "protein": row.protein,
            "carbs": row.carbs,
            "fat": row.fat,
            "items": [],
        }
    )


@router.get("/template/{template_id}", response_model=ShareCode)
def share_meal_template(
    template_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Encode a saved template, ingredient rows included.

    The better thing to share: the recipient can adjust the rice on its own
    instead of scaling one lump. Reuses _items_of, so a template whose
    items_json is unreadable shares as totals-only rather than failing -- the
    same tolerance the dashboard already relies on.
    """
    row = db.scalar(
        select(MealTemplateRow).where(
            MealTemplateRow.id == template_id,
            MealTemplateRow.user_id == user.id,
        )
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Meal template not found")
    return _code_for(
        {
            "name": row.name,
            "calories": row.calories,
            "protein": row.protein,
            "carbs": row.carbs,
            "fat": row.fat,
            "items": [item.model_dump() for item in _items_of(row)],
        }
    )


@router.post("/decode", response_model=SharedMeal)
def decode_meal_code(
    body: ShareDecodeRequest,
    user: User = Depends(get_current_user),
):
    """Read a code. Writes nothing -- 200, not 201.

    POST rather than GET despite being a pure read: a code runs to hundreds of
    characters and would strain query-string limits, and a URL is written to the
    edge access log while a body is not.

    Takes no db session. Nothing here touches the database, which is the clearest
    statement available that decoding cannot reach anyone's rows.
    """
    try:
        payload = decode_share_code(body.code)
    except ShareCodeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    try:
        return SharedMeal.model_validate(payload)
    except ValidationError as exc:
        # A ValidationError raised *inside* a handler is not FastAPI's 422 path
        # -- that only covers request parsing -- so uncaught this would be a 500
        # for input the server had already understood and refused.
        logger.warning("share code failed shape validation: %s", exc.errors())
        raise HTTPException(status_code=400, detail=_SHAPE_REFUSAL) from None
