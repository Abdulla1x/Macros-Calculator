"""CSV export/import of the meals table."""
import csv
import io
from datetime import datetime

from fastapi import APIRouter, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..db import get_connection
from ..schemas import ImportResult

router = APIRouter(prefix="/api/data", tags=["data"])

CSV_COLUMNS = ["date", "name", "calories", "protein", "carbs", "fat"]
ACCEPTED_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y")


@router.get("/export")
def export_csv():
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT date, name, calories, protein, carbs, fat FROM meals ORDER BY date, id"
        ).fetchall()
    finally:
        conn.close()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    writer.writerows([tuple(row) for row in rows])
    buffer.seek(0)

    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=macros_backup.csv"},
    )


def _parse_date(raw: str) -> str | None:
    raw = raw.strip()
    for fmt in ACCEPTED_DATE_FORMATS:
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
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
async def import_csv(file: UploadFile):
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
    conn = get_connection()
    try:
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

            duplicate = conn.execute(
                """SELECT 1 FROM meals
                   WHERE date = ? AND name = ? AND calories = ? AND protein = ?""",
                (date, name, calories, protein),
            ).fetchone()
            if duplicate:
                skipped_duplicates += 1
                continue

            conn.execute(
                """INSERT INTO meals (date, name, calories, protein, carbs, fat)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (date, name, calories, protein, carbs, fat),
            )
            inserted += 1
        conn.commit()
    finally:
        conn.close()

    return ImportResult(
        inserted=inserted,
        skipped_duplicates=skipped_duplicates,
        skipped_invalid=skipped_invalid,
    )
