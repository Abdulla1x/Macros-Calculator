import json

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import Setting, User
from ..schemas import BodyTargets, Settings
from ..targets import apply_auto_targets, compute_targets

router = APIRouter(prefix="/api/settings", tags=["settings"])

# The fields that are patched rather than replaced. See the note on
# update_settings for why these behave differently from the seven original ones.
#
# Named for the behaviour, not the feature: this began as the body profile and
# is now the body profile, the tracker goals and the weigh-in reminder, and
# every field added from here on joins this group rather than the replaced one.
#
# `water_quick_adds` is patched too but is NOT in this tuple -- it is the one
# field whose schema name and column name differ, so it cannot go through the
# generic setattr below. It is handled explicitly, just after the loop.
_PATCHED_FIELDS = (
    "height_cm",
    "birth_date",
    "sex",
    "activity_level",
    "goal_rate_kg_per_week",
    "targets_auto",
    "water_goal_ml",
    "steps_goal",
    "weigh_in_reminder_time",
    "weigh_in_reminder_days",
)


def _settings_out(row: Setting) -> Settings:
    """Build the response explicitly, rather than letting Pydantic read the row.

    `Settings` is a from_attributes model, so returning the ORM row directly
    works for every field whose name matches its column -- which is all of them
    but one. `water_quick_adds` is a list[float] on the API and
    `water_quick_adds_json` is TEXT in the database, and that divergence is
    exactly the trap this codebase has now hit three times: `UserOut.is_admin`
    silently returned False, `MealTemplate.items` silently returned [], and
    here it would be louder but worse -- Pydantic would be handed a JSON
    *string* for a list field and every GET /api/settings would 500.

    One construction site, the same fix `_user_out` and `_template_out` are.
    """
    data = Settings.model_validate(row).model_dump()
    data["water_quick_adds"] = (
        None if row.water_quick_adds_json is None
        else json.loads(row.water_quick_adds_json)
    )
    return Settings.model_validate(data)


def _get_or_create(db: Session, user_id: int) -> Setting:
    # Signup creates the row; this covers accounts that predate that behavior.
    row = db.get(Setting, user_id)
    if row is None:
        row = Setting(user_id=user_id)
        db.add(row)
        db.commit()
    return row


@router.get("", response_model=Settings)
def get_settings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return _settings_out(_get_or_create(db, user.id))


@router.get("/targets", response_model=BodyTargets)
def get_targets(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """BMI, BMR, TDEE and a calorie/macro target from the profile and the logs.

    The TDEE is measured from energy balance where the logs can support it and
    estimated from the Mifflin-St Jeor formula where they cannot; `tdee_source`
    says which, and `tdee_basis` says what it was built from or what it is still
    short of. Both are always populated, so the card never has to guess.

    Read-only and always 200, even when nothing can be computed: an incomplete
    profile is an ordinary state, not an error, and the `missing` list is the
    answer in that case. Everything here is derived on the fly -- the only
    numbers this feature *stores* are the four goals, and only when
    `targets_auto` is on.
    """
    return compute_targets(db, _get_or_create(db, user.id))


@router.put("", response_model=Settings)
def update_settings(
    settings: Settings,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save settings. Two write semantics in one handler, deliberately.

    The original goal and tracking fields are **replaced** on every PUT,
    exactly as they always have been. Everything added since -- the body
    profile, and now the two water fields -- is **patched**: each is written
    only if the request actually contained it.

    The asymmetry buys one specific thing. This app is an installed PWA, so a
    tab opened before a deploy keeps running the old bundle until it is
    reloaded -- for days, on a phone. A client that predates the body profile
    PUTs a body without those keys, and under replace semantics that would
    silently blank the user's height, birth date and sex on their next save,
    and move their targets with it. `model_fields_set` distinguishes "did not
    send" from "sent null", so clearing a field on purpose still works.

    That reasoning is why the water fields joined the patched group on day one
    rather than after a phone somewhere quietly wiped someone's goal.

    When `targets_auto` is on the four submitted goals are ignored and
    recomputed from the profile; the client sends them anyway because the
    schema requires them, and they are what the server last stored.
    """
    row = _get_or_create(db, user.id)
    row.calorie_goal = settings.calorie_goal
    row.protein_goal = settings.protein_goal
    row.carbs_goal = settings.carbs_goal
    row.fat_goal = settings.fat_goal
    row.track_carbs = settings.track_carbs
    row.track_fat = settings.track_fat
    row.weight_unit = settings.weight_unit

    for field in _PATCHED_FIELDS:
        if field in settings.model_fields_set:
            setattr(row, field, getattr(settings, field))

    # Out of the loop because the name and the type both change on the way in.
    # Sending null clears it back to the shipped defaults, which is why this is
    # keyed on model_fields_set rather than on the value being non-None.
    if "water_quick_adds" in settings.model_fields_set:
        row.water_quick_adds_json = (
            None if settings.water_quick_adds is None
            else json.dumps(settings.water_quick_adds)
        )

    # After the profile is in place, never before -- targets_auto and the
    # fields it reads are both assigned in the loop above.
    apply_auto_targets(row, db)
    db.commit()
    return _settings_out(row)
