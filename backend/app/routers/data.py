"""CSV export/import of the meals table, plus a full JSON export of all data."""
import csv
import io
import json
from datetime import date as date_type
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import AIAnalysis, Food, Meal, MealTemplate, Setting, User, WeightEntry
from ..schemas import ImportResult

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
    """Returns (value, ok). Optional empty values are (None, True)."""
    if raw is None or str(raw).strip() == "":
        return None, not required
    try:
        value = float(raw)
        return (value, True) if value >= 0 else (None, False)
    except ValueError:
        return None, False


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
