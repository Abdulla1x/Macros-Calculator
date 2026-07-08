"""CSV export/import of the meals table."""
import csv
import io
from datetime import date as date_type
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Meal
from ..schemas import ImportResult

router = APIRouter(prefix="/api/data", tags=["data"])

CSV_COLUMNS = ["date", "name", "calories", "protein", "carbs", "fat"]
ACCEPTED_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y")


@router.get("/export")
def export_csv(db: Session = Depends(get_db)):
    rows = db.scalars(select(Meal).order_by(Meal.date, Meal.id)).all()

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
async def import_csv(file: UploadFile, db: Session = Depends(get_db)):
    content = (await file.read()).decode("utf-8-sig", errors="replace")
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

        duplicate = db.scalars(
            select(Meal.id).where(
                Meal.date == date,
                Meal.name == name,
                Meal.calories == calories,
                Meal.protein == protein,
            )
        ).first()
        if duplicate is not None:
            skipped_duplicates += 1
            continue

        db.add(
            Meal(date=date, name=name, calories=calories, protein=protein,
                 carbs=carbs, fat=fat)
        )
        db.flush()
        inserted += 1
    db.commit()

    return ImportResult(
        inserted=inserted,
        skipped_duplicates=skipped_duplicates,
        skipped_invalid=skipped_invalid,
    )
