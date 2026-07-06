from fastapi import APIRouter

from ..db import get_connection
from ..schemas import Settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=Settings)
def get_settings():
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM settings WHERE id = 1").fetchone()
        return _to_schema(row)
    finally:
        conn.close()


@router.put("", response_model=Settings)
def update_settings(settings: Settings):
    conn = get_connection()
    try:
        conn.execute(
            """UPDATE settings SET
                   calorie_goal = ?, protein_goal = ?, carbs_goal = ?, fat_goal = ?,
                   track_carbs = ?, track_fat = ?
               WHERE id = 1""",
            (settings.calorie_goal, settings.protein_goal, settings.carbs_goal,
             settings.fat_goal, int(settings.track_carbs), int(settings.track_fat)),
        )
        conn.commit()
        return settings
    finally:
        conn.close()


def _to_schema(row) -> Settings:
    return Settings(
        calorie_goal=row["calorie_goal"],
        protein_goal=row["protein_goal"],
        carbs_goal=row["carbs_goal"],
        fat_goal=row["fat_goal"],
        track_carbs=bool(row["track_carbs"]),
        track_fat=bool(row["track_fat"]),
    )
