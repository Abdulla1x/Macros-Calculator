from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..auth.deps import get_current_user
from ..db import get_db
from ..models import Setting, User
from ..schemas import Settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


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
    return _get_or_create(db, user.id)


@router.put("", response_model=Settings)
def update_settings(
    settings: Settings,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    row = _get_or_create(db, user.id)
    row.calorie_goal = settings.calorie_goal
    row.protein_goal = settings.protein_goal
    row.carbs_goal = settings.carbs_goal
    row.fat_goal = settings.fat_goal
    row.track_carbs = settings.track_carbs
    row.track_fat = settings.track_fat
    db.commit()
    return row
