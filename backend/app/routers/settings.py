from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Setting
from ..schemas import Settings

router = APIRouter(prefix="/api/settings", tags=["settings"])

# Placeholder single-tenant key until auth lands (Phase 3 scopes this per user).
LEGACY_USER_ID = 1


def _get_or_create(db: Session, user_id: int) -> Setting:
    row = db.get(Setting, user_id)
    if row is None:
        row = Setting(user_id=user_id)
        db.add(row)
        db.commit()
    return row


@router.get("", response_model=Settings)
def get_settings(db: Session = Depends(get_db)):
    return _get_or_create(db, LEGACY_USER_ID)


@router.put("", response_model=Settings)
def update_settings(settings: Settings, db: Session = Depends(get_db)):
    row = _get_or_create(db, LEGACY_USER_ID)
    row.calorie_goal = settings.calorie_goal
    row.protein_goal = settings.protein_goal
    row.carbs_goal = settings.carbs_goal
    row.fat_goal = settings.fat_goal
    row.track_carbs = settings.track_carbs
    row.track_fat = settings.track_fat
    db.commit()
    return row
