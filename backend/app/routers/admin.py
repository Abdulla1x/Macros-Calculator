"""Operator metrics: how many people use this app, and how much.

PRIVACY BOUNDARY — read this before adding a field.

Every other router here is scoped to the authenticated user. This one
deliberately is not, which is exactly why it is the only router behind
`require_admin`. What it may expose is **counts, dates and account
identifiers**: email, signup date, last-active, and how many meals, weigh-ins,
foods, saved meal templates, water logs, step-count days, supplements and
doses ticked each account has.

Admins do **not** see meal names, weight values, food entries, meal-template
names, **supplement names or doses**, how much anyone drank or walked, or
voice-note transcripts. The supplement names matter most of that list: a
supplement list can name a prescription, which makes it the most disclosive
data this app stores, and a count of rows says everything an operator needs
while saying nothing about anyone's health. That is what keeps README.md's "every API endpoint is scoped to the
authenticated user" and the Settings privacy copy true without a rewrite.
`tests/test_admin.py` asserts the absence positively, so a later "just one
useful field" commit fails a test rather than quietly failing the promise.

If per-user drill-down is ever wanted, it goes behind a consent toggle the user
themselves flips — never an admin override. This is the kind of constraint that
erodes one convenient field at a time, which is why it is written down here
rather than remembered.
"""
from collections import defaultdict
from datetime import date as date_type
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth.deps import require_admin
from ..db import get_db
from ..models import (
    AIAnalysis,
    Food,
    Meal,
    MealTemplate,
    StepEntry,
    Supplement,
    SupplementLog,
    User,
    WaterLog,
    WeightEntry,
)
from ..schemas import AdminDailyActivity, AdminDailyCount, AdminStats, AdminUserRow
from .ai import calls_today, global_daily_limit

router = APIRouter(prefix="/api/admin", tags=["admin"])

# The chart width, and the "is anyone here this week" window inside it. Both
# are whole UTC days, matching the boundary calls_today already uses — mixing
# a local-day window with a UTC-day counter on the same screen is how two
# numbers that should agree stop agreeing.
CHART_DAYS = 30
ACTIVE_WINDOW_DAYS = 7

# No rate limiting, per rate_limit.py's rule: only the auth endpoints are
# limited, because everything else already requires a valid token — and this
# one additionally requires being on the allowlist.

# Tables that record a real creation timestamp, so activity can be read off
# them directly. Meals are handled separately: see _meal_activity_at.
#
# Membership is not "never upserted" -- WeightEntry and StepEntry both upsert.
# The rule that actually holds is what the common write *does*: where it adds a
# new row for a new date, created_at is a fresh timestamp and means what this
# tuple assumes. Weigh-ins, step counts, foods, water and AI calls are all that
# shape. WaterLog is the purest case, every row an insert, and the truest
# engagement signal the app has -- someone tapping "+250" four times a day is
# using it on days they may not log a single meal.
#
# MealTemplate is counted per user below but deliberately NOT listed, because
# its common write rewrites an *old* row: re-saving Breakfast from the log-meal
# footer leaves created_at on the day the template was first made, so today's
# use would register as activity months ago. That is the same backwards reading
# _meal_activity_at exists to prevent, and no signal is lost -- the button
# lives in the log-meal footer, so a template save always rides along with a
# meal write in the same session.
#
# The residual, accepted knowingly: correcting a *past* day's count on a later
# day does not move last_active_at, because the row it rewrites already exists.
# That undercounts a session spent only fixing history, for steps exactly as it
# already does for a re-logged weigh-in. Logging the current day -- the common
# case for both -- is a fresh row and reads correctly.
#
# Supplement follows MealTemplate out of this tuple for the same reason and
# is counted below without joining it: the list is written once and then
# edited by PUT, so a rename today would register as activity on the day it
# was first added. Its check-offs are the signal instead, and they are the
# WaterLog shape exactly -- a fresh row every time a box is ticked.
_TIMESTAMPED = (WeightEntry, Food, AIAnalysis, WaterLog, StepEntry, SupplementLog)


def _meal_activity_at(created_at: datetime | None, eaten_on: date_type) -> datetime:
    """When a meal row counts as *app usage*.

    `created_at` where we have it; the eaten date at midnight where we don't.
    Rows written before migration 0006 land in the second case, so history
    still charts — just at eat-date precision instead of vanishing.
    """
    if created_at is not None:
        return created_at
    return datetime.combine(eaten_on, time.min)


def _count_by_user(db: Session, model, user_ids: list[int]) -> dict[int, int]:
    """{user_id: row count} for one table, in one grouped query.

    One query per table, not one per user: a fixed handful of queries whether
    there are three accounts or three thousand. The obvious alternative —
    looping the users and counting inside the loop — is N queries per table and
    gets slower in exact proportion to the app succeeding.
    """
    rows = db.execute(
        select(model.user_id, func.count())
        .where(model.user_id.in_(user_ids))
        .group_by(model.user_id)
    ).all()
    return {user_id: count for user_id, count in rows}


def _last_active_by_user(db: Session, user_ids: list[int]) -> dict[int, datetime]:
    """{user_id: latest activity timestamp} across every table that records one.

    Derived rather than stored. A `last_seen` column would be more direct, but
    keeping it accurate means a write on every authenticated request — turning
    every read into a write for a number nobody reads in real time.

    Meals contribute `max(created_at)` and `max(date)` as two separate
    aggregates combined in Python, not a SQL COALESCE. COALESCE of a DateTime
    with a Date types differently on SQLite and Postgres, and this project runs
    SQLite in dev and test and Postgres in production — so the expression that
    passed locally is not the one that would run live.
    """
    latest: dict[int, datetime] = {}

    def offer(user_id: int, value: datetime | None) -> None:
        if value is None:
            return
        current = latest.get(user_id)
        if current is None or value > current:
            latest[user_id] = value

    for model in _TIMESTAMPED:
        rows = db.execute(
            select(model.user_id, func.max(model.created_at))
            .where(model.user_id.in_(user_ids))
            .group_by(model.user_id)
        ).all()
        for user_id, value in rows:
            offer(user_id, value)

    meal_rows = db.execute(
        select(Meal.user_id, func.max(Meal.created_at), func.max(Meal.date))
        .where(Meal.user_id.in_(user_ids))
        .group_by(Meal.user_id)
    ).all()
    for user_id, newest_created, newest_date in meal_rows:
        offer(user_id, newest_created)
        if newest_date is not None:
            offer(user_id, datetime.combine(newest_date, time.min))

    return latest


@router.get("/users", response_model=list[AdminUserRow])
def list_users(
    limit: int = Query(default=100, ge=1, le=500),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """Per-account metrics, newest signups first."""
    users = db.scalars(
        select(User).order_by(User.created_at.desc(), User.id.desc()).limit(limit)
    ).all()
    if not users:
        return []

    ids = [u.id for u in users]
    meals = _count_by_user(db, Meal, ids)
    weights = _count_by_user(db, WeightEntry, ids)
    foods = _count_by_user(db, Food, ids)
    templates = _count_by_user(db, MealTemplate, ids)
    ai_calls = _count_by_user(db, AIAnalysis, ids)
    water_logs = _count_by_user(db, WaterLog, ids)
    steps = _count_by_user(db, StepEntry, ids)
    supplements = _count_by_user(db, Supplement, ids)
    supplement_logs = _count_by_user(db, SupplementLog, ids)
    last_active = _last_active_by_user(db, ids)

    return [
        AdminUserRow(
            id=u.id,
            email=u.email,
            created_at=u.created_at,
            last_active_at=last_active.get(u.id),
            meals=meals.get(u.id, 0),
            weights=weights.get(u.id, 0),
            foods=foods.get(u.id, 0),
            meal_templates=templates.get(u.id, 0),
            ai_calls=ai_calls.get(u.id, 0),
            water_logs=water_logs.get(u.id, 0),
            steps=steps.get(u.id, 0),
            supplements=supplements.get(u.id, 0),
            supplement_logs=supplement_logs.get(u.id, 0),
        )
        for u in users
    ]


@router.get("/stats", response_model=AdminStats)
def stats(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """App-wide totals plus the two daily series the dashboard charts."""
    today = datetime.now(timezone.utc).date()
    first_day = today - timedelta(days=CHART_DAYS - 1)
    window_start = datetime.combine(first_day, time.min)
    days = [first_day + timedelta(days=offset) for offset in range(CHART_DAYS)]

    total_users = db.scalar(select(func.count()).select_from(User))
    total_meals = db.scalar(select(func.count()).select_from(Meal))

    signups_per_day: dict[date_type, int] = defaultdict(int)
    for created_at in db.scalars(
        select(User.created_at).where(User.created_at >= window_start)
    ).all():
        signups_per_day[created_at.date()] += 1

    # Bucketing by day happens in Python, not SQL, for the same reason the
    # COALESCE above does: SQLite has no real date type, so func.date() and
    # CAST(x AS DATE) do not agree across the two backends this app runs on.
    # calls_today set that precedent — its UTC midnight is computed in Python
    # precisely so SQLite and Postgres behave identically. At a 30-day window
    # and this app's volume the fetched rows number in the thousands, which is
    # nothing; if that ever stops being true, the fix is a dialect-aware
    # expression, not an untested one.
    meals_per_day: dict[date_type, int] = defaultdict(int)
    active_per_day: dict[date_type, set[int]] = defaultdict(set)

    # `or_` because the two columns answer different questions and either can
    # put a row in the window: a NULL created_at row is only reachable by its
    # date, and a row created recently but backdated far away is only reachable
    # by created_at. Over-fetching slightly is fine — _meal_activity_at decides
    # the real day and anything outside the window is dropped below.
    meal_rows = db.execute(
        select(Meal.user_id, Meal.created_at, Meal.date).where(
            or_(Meal.created_at >= window_start, Meal.date >= first_day)
        )
    ).all()
    for user_id, created_at, eaten_on in meal_rows:
        day = _meal_activity_at(created_at, eaten_on).date()
        if first_day <= day <= today:
            meals_per_day[day] += 1
            active_per_day[day].add(user_id)

    for model in _TIMESTAMPED:
        rows = db.execute(
            select(model.user_id, model.created_at).where(
                model.created_at >= window_start
            )
        ).all()
        for user_id, created_at in rows:
            day = created_at.date()
            if day <= today:
                active_per_day[day].add(user_id)

    def distinct_active(window: list[date_type]) -> int:
        """Distinct accounts active across a window — not the sum of daily
        counts, which would count one person logging every day as seven."""
        seen: set[int] = set()
        for day in window:
            seen |= active_per_day.get(day, set())
        return len(seen)

    recent = days[-ACTIVE_WINDOW_DAYS:]
    ai_by_kind = db.execute(
        select(AIAnalysis.kind, func.count())
        .where(AIAnalysis.created_at >= window_start)
        .group_by(AIAnalysis.kind)
    ).all()

    return AdminStats(
        total_users=total_users,
        total_meals=total_meals,
        signups_7d=sum(signups_per_day.get(day, 0) for day in recent),
        signups_30d=sum(signups_per_day.get(day, 0) for day in days),
        active_7d=distinct_active(recent),
        active_30d=distinct_active(days),
        meals_7d=sum(meals_per_day.get(day, 0) for day in recent),
        ai_calls_today=calls_today(db),
        ai_global_daily_limit=global_daily_limit(),
        ai_calls_30d_by_kind={kind: count for kind, count in ai_by_kind},
        window_days=CHART_DAYS,
        # Every day in the window is emitted, including empty ones. A series
        # that only carries days with data makes a chart draw a straight line
        # across a gap, which reads as steady use during a week nobody opened
        # the app.
        signups=[
            AdminDailyCount(date=day, count=signups_per_day.get(day, 0))
            for day in days
        ],
        activity=[
            AdminDailyActivity(
                date=day,
                active_users=len(active_per_day.get(day, set())),
                meals=meals_per_day.get(day, 0),
            )
            for day in days
        ],
    )
