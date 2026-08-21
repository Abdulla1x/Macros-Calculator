"""CSV export/import of the meals table, plus a full JSON export of all data."""
import csv
import io
import json
import math
from datetime import date as date_type
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import (
    AIAnalysis,
    Food,
    Meal,
    MealTemplate,
    Setting,
    StepEntry,
    User,
    WaterLog,
    WeightEntry,
)
from ..schemas import (
    FUTURE_DATE_GRACE_DAYS,
    MAX_STEPS_PER_DAY,
    ImportResult,
)

router = APIRouter(prefix="/api/data", tags=["data"])

CSV_COLUMNS = ["date", "name", "calories", "protein", "carbs", "fat"]
ACCEPTED_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y")
MAX_IMPORT_BYTES = 1024 * 1024  # 1 MB — far beyond any realistic meal history


@router.get("/export")
def export_csv(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(Meal).where(Meal.user_id == user.id).order_by(Meal.date, Meal.id)
    ).all()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    writer.writerows(
        (row.date.isoformat(), row.name, row.calories, row.protein, row.carbs, row.fat)
        for row in rows
    )
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=macros_backup.csv"},
    )


@router.get("/export/all")
def export_all(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Everything the account owns, as JSON (data portability)."""
    meals = db.scalars(
        select(Meal).where(Meal.user_id == user.id).order_by(Meal.date, Meal.id)
    ).all()
    foods = db.scalars(
        select(Food).where(Food.user_id == user.id).order_by(Food.id)
    ).all()
    weights = db.scalars(
        select(WeightEntry)
        .where(WeightEntry.user_id == user.id)
        .order_by(WeightEntry.date)
    ).all()
    templates = db.scalars(
        select(MealTemplate)
        .where(MealTemplate.user_id == user.id)
        .order_by(MealTemplate.id)
    ).all()
    water = db.scalars(
        select(WaterLog)
        .where(WaterLog.user_id == user.id)
        .order_by(WaterLog.date, WaterLog.id)
    ).all()
    steps = db.scalars(
        select(StepEntry)
        .where(StepEntry.user_id == user.id)
        .order_by(StepEntry.date, StepEntry.id)
    ).all()
    setting = db.get(Setting, user.id)
    analyses = db.scalars(
        select(AIAnalysis)
        .where(AIAnalysis.user_id == user.id)
        .order_by(AIAnalysis.id)
    ).all()

    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "user": {"email": user.email, "created_at": user.created_at.isoformat()},
        "settings": None if setting is None else {
            "calorie_goal": setting.calorie_goal,
            "protein_goal": setting.protein_goal,
            "carbs_goal": setting.carbs_goal,
            "fat_goal": setting.fat_goal,
            "track_carbs": setting.track_carbs,
            "track_fat": setting.track_fat,
            "weight_unit": setting.weight_unit,
            "height_cm": setting.height_cm,
            # ISO date, or null. Exported as the date it is, not as an age:
            # an age would be a derived number that goes stale inside a file
            # the user keeps.
            "birth_date": (
                None if setting.birth_date is None
                else setting.birth_date.isoformat()
            ),
            "sex": setting.sex,
            "activity_level": setting.activity_level,
            "goal_rate_kg_per_week": setting.goal_rate_kg_per_week,
            "targets_auto": setting.targets_auto,
            # Null means "derived from my weight" rather than "unset", so it
            # exports as null and the meaning travels in this comment.
            "water_goal_ml": setting.water_goal_ml,
            # Exported as the list the API speaks, not the JSON string the
            # column stores -- an export is for the user, not for the schema.
            "water_quick_adds": (
                None if setting.water_quick_adds_json is None
                else json.loads(setting.water_quick_adds_json)
            ),
            # Null here means "no goal set" -- the opposite of water_goal_ml
            # above, where null means "derive it". Same shape, different claim.
            "steps_goal": setting.steps_goal,
        },
        "meals": [
            # `date` is when it was eaten, `created_at` when it was logged.
            # The latter is null for rows written before migration 0006 and is
            # exported as null rather than guessed at -- this endpoint promises
            # everything the account owns, including the gaps.
            {"date": m.date.isoformat(),
             "created_at": m.created_at.isoformat() if m.created_at else None,
             "name": m.name, "calories": m.calories,
             "protein": m.protein, "carbs": m.carbs, "fat": m.fat}
            for m in meals
        ],
        "foods": [
            {"name": f.name, "serving_size": f.serving_size, "calories": f.calories,
             "protein": f.protein, "carbs": f.carbs, "fat": f.fat, "source": f.source}
            for f in foods
        ],
        "weights": [
            {"date": w.date.isoformat(), "weight_kg": w.weight_kg}
            for w in weights
        ],
        "water_logs": [
            # Event rows, so created_at is what orders two drinks on one day
            # and is part of the data rather than metadata about it.
            {"date": w.date.isoformat(), "ml": w.ml,
             "created_at": w.created_at.isoformat() if w.created_at else None}
            for w in water
        ],
        "steps": [
            # One row per day, so created_at is when the count was first
            # written and not when it was last corrected -- metadata about the
            # row rather than part of the day, which is why it is not exported.
            {"date": s.date.isoformat(), "steps": s.steps}
            for s in steps
        ],
        "meal_templates": [
            # Same empty-string guard as ai_analyses below: items_json is
            # nullable, and json.loads("") raises.
            {"name": t.name, "calories": t.calories, "protein": t.protein,
             "carbs": t.carbs, "fat": t.fat,
             "created_at": t.created_at.isoformat(),
             "items": json.loads(t.items_json) if t.items_json else []}
            for t in templates
        ],
        "ai_analyses": [
            # Transcription rows carry no analysis JSON (models.py documents
            # this), and json.loads("") raises — which used to 500 the whole
            # export for anyone who had ever recorded a voice note. Probe rows
            # are dropped entirely: they are operational noise, not user data.
            {"created_at": a.created_at.isoformat(), "kind": a.kind,
             "user_text": a.user_text,
             "analysis": json.loads(a.analysis_json) if a.analysis_json else None,
             "meal_id": a.meal_id}
            for a in analyses if a.kind != "probe"
        ],
    }


def _parse_date(raw: str) -> date_type | None:
    raw = raw.strip()
    for fmt in ACCEPTED_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _parse_float(raw, required: bool) -> tuple[float | None, bool]:
    """Returns (value, ok). Optional empty values are (None, True).

    The isfinite check is the one that is easy to leave out, and this importer
    is the only path that writes a Meal without going through MealCreate -- so
    the bound on that schema does not protect it. `float()` parses "Infinity",
    "inf" and "1e999" alike, and `inf >= 0` is True, so without this a single
    CSV row could store a value that 500s the account's export and reads back
    as null everywhere else. `nan` fails the >= 0 comparison on its own.
    """
    if raw is None or str(raw).strip() == "":
        return None, not required
    try:
        value = float(raw)
        return (value, True) if math.isfinite(value) and value >= 0 else (None, False)
    except ValueError:
        return None, False


def _parse_steps(raw) -> tuple[int | None, bool]:
    """Returns (value, ok) for a step count. Never optional -- a row without one
    is not a row.

    Four rejections, and the last two are the ones a plainer `int(raw)` would
    get wrong in opposite directions. Non-finite comes straight from
    `_parse_float`'s lesson: this importer is the only path that writes a
    StepEntry without going through StepEntryCreate, so the schema's bounds do
    not protect it, and `float("1e999")` is `inf` with `inf >= 0` True.
    Fractional is the new one: `int("8000.5")` raises rather than truncating,
    so parsing through float first is what lets a half-step be *reported* as a
    bad row instead of blowing up the whole file.
    """
    if raw is None or str(raw).strip() == "":
        return None, False
    try:
        value = float(raw)
    except ValueError:
        return None, False
    if not math.isfinite(value) or value < 0 or value > MAX_STEPS_PER_DAY:
        return None, False
    if not value.is_integer():
        return None, False
    return int(value), True


@router.post("/import/steps", response_model=ImportResult)
async def import_steps_csv(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Import a step history from a two-column `date,steps` CSV.

    Deliberately generic rather than tuned to any one phone's export, because
    only one of the four is simple and it is not testable here. Samsung Health's
    `step_daily_trend` file is already one row per day and drops in; Apple
    Health ships a single 200 MB+ XML of per-sample records whose iPhone/Watch
    duplicates cannot be resolved reliably, Health Connect ships a SQLite
    database, and Huawei mails a zip of per-activity JSON hours later. A parser
    for any of those would be guessing at a file nobody here has, and a step
    history silently inflated by double-counted samples is worse than no import
    at all -- nothing on screen would look wrong.

    So: one honest format, extra columns ignored, and a per-row count of what
    was refused. Anyone else converts once, which the Settings copy says.

    Nothing here recomputes calorie targets, matching the meals importer above
    and routers/steps.py. Steps are an input to no target.
    """
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="CSV too large (max 1 MB).")
    content = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="Empty CSV file")

    fields = {name.strip().lower() for name in reader.fieldnames}
    if not {"date", "steps"}.issubset(fields):
        raise HTTPException(
            status_code=400,
            detail="Invalid CSV format. Required columns: date, steps",
        )

    # The same grace the manual path allows, so an import is not a hole through
    # a rule the form enforces.
    future_limit = date_type.today() + timedelta(days=FUTURE_DATE_GRACE_DAYS)

    inserted = skipped_duplicates = skipped_invalid = 0
    for row in reader:
        row = {(k or "").strip().lower(): v for k, v in row.items()}

        date = _parse_date(row.get("date") or "")
        steps, steps_ok = _parse_steps(row.get("steps"))

        if not (date and steps_ok) or date > future_limit:
            skipped_invalid += 1
            continue

        # A collision is a *date*, not a whole row -- `steps` is unique on
        # (user_id, date). Skipped rather than overwritten, on purpose: a count
        # already stored was either typed by hand or imported earlier, and
        # replacing it from a file is not recoverable. The flush below means a
        # file containing the same date twice hits this on the second one.
        existing = db.scalars(
            select(StepEntry.id).where(
                StepEntry.user_id == user.id, StepEntry.date == date
            )
        ).first()
        if existing is not None:
            skipped_duplicates += 1
            continue

        db.add(StepEntry(user_id=user.id, date=date, steps=steps))
        db.flush()
        inserted += 1
    db.commit()

    return ImportResult(
        inserted=inserted,
        skipped_duplicates=skipped_duplicates,
        skipped_invalid=skipped_invalid,
    )


@router.post("/import", response_model=ImportResult)
async def import_csv(
    file: UploadFile,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    raw = await file.read(MAX_IMPORT_BYTES + 1)
    if len(raw) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="CSV too large (max 1 MB).")
    content = raw.decode("utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None:
        raise HTTPException(status_code=400, detail="Empty CSV file")

    fields = {name.strip().lower() for name in reader.fieldnames}
    required = {"date", "name", "calories", "protein"}
    if not required.issubset(fields):
        raise HTTPException(
            status_code=400,
            detail="Invalid CSV format. Required columns: date, name, calories, protein",
        )

    inserted = skipped_duplicates = skipped_invalid = 0
    for row in reader:
        row = {(k or "").strip().lower(): v for k, v in row.items()}

        date = _parse_date(row.get("date") or "")
        name = (row.get("name") or "").strip()
        calories, cal_ok = _parse_float(row.get("calories"), required=True)
        protein, pro_ok = _parse_float(row.get("protein"), required=True)
        carbs, carbs_ok = _parse_float(row.get("carbs"), required=False)
        fat, fat_ok = _parse_float(row.get("fat"), required=False)

        if not (date and name and cal_ok and pro_ok and carbs_ok and fat_ok):
            skipped_invalid += 1
            continue

        # All macros participate in the match; SQLAlchemy renders `== None`
        # as IS NULL, so rows with absent carbs/fat still dedupe correctly.
        duplicate = db.scalars(
            select(Meal.id).where(
                Meal.user_id == user.id,
                Meal.date == date,
                Meal.name == name,
                Meal.calories == calories,
                Meal.protein == protein,
                Meal.carbs == carbs,
                Meal.fat == fat,
            )
        ).first()
        if duplicate is not None:
            skipped_duplicates += 1
            continue

        db.add(
            Meal(user_id=user.id, date=date, name=name, calories=calories,
                 protein=protein, carbs=carbs, fat=fat)
        )
        db.flush()
        inserted += 1
    db.commit()

    return ImportResult(
        inserted=inserted,
        skipped_duplicates=skipped_duplicates,
        skipped_invalid=skipped_invalid,
    )
