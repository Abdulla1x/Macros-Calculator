"""What counts as an account being *active* on a given day.

One definition, two consumers. /admin's live charts derive activity from
whatever rows exist right now; app/snapshots.py freezes the same figure into
daily_stats so it survives an account deletion. If those two ever disagreed
about what "active" means, the chart and the history would tell different
stories about the same Tuesday and there would be no way to tell which was
right -- so they share this module rather than each computing it.

Moved here from routers/admin.py, comments intact, when snapshots.py needed the
second caller.
"""
from collections import defaultdict
from datetime import date as date_type
from datetime import datetime, time

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import (
    AIAnalysis,
    CaloriePlanDay,
    Food,
    Meal,
    StepEntry,
    SupplementLog,
    WaterLog,
    WeightEntry,
)

# Tables that record a real creation timestamp, so activity can be read off
# them directly. Meals are handled separately: see meal_activity_at.
#
# Membership is not "never upserted" -- WeightEntry and StepEntry both upsert.
# The rule that actually holds is what the common write *does*: where it adds a
# new row for a new date, created_at is a fresh timestamp and means what this
# tuple assumes. Weigh-ins, step counts, foods, water and AI calls are all that
# shape. WaterLog is the purest case, every row an insert, and the truest
# engagement signal the app has -- someone tapping "+250" four times a day is
# using it on days they may not log a single meal.
#
# MealTemplate is counted per user in admin.py but deliberately NOT listed,
# because its common write rewrites an *old* row: re-saving Breakfast from the
# log-meal footer leaves created_at on the day the template was first made, so
# today's use would register as activity months ago. That is the same backwards
# reading meal_activity_at exists to prevent, and no signal is lost -- the
# button lives in the log-meal footer, so a template save always rides along
# with a meal write in the same session.
#
# The residual, accepted knowingly: correcting a *past* day's count on a later
# day does not move last_active_at, because the row it rewrites already exists.
# That undercounts a session spent only fixing history, for steps exactly as it
# already does for a re-logged weigh-in. Logging the current day -- the common
# case for both -- is a fresh row and reads correctly.
#
# Supplement follows MealTemplate out of this tuple for the same reason and
# is counted in admin.py without joining it: the list is written once and then
# edited by PUT, so a rename today would register as activity on the day it
# was first added. Its check-offs are the signal instead, and they are the
# WaterLog shape exactly -- a fresh row every time a box is ticked.
#
# CaloriePlanDay joins the tuple and passes the rule cleanly, which is worth
# saying because the other per-date tables here needed an argument. There is no
# update path at all: the unique index on (user_id, date) means a plan cannot
# be edited in place, only cancelled and made again, so every row's created_at
# is the moment a plan was actually made. Making one is also about as deliberate
# an act as this app has -- nobody plans a Saturday by accident.
TIMESTAMPED = (
    WeightEntry, Food, AIAnalysis, WaterLog, StepEntry, SupplementLog,
    CaloriePlanDay,
)


def meal_activity_at(created_at: datetime | None, eaten_on: date_type) -> datetime:
    """When a meal row counts as *app usage*.

    `created_at` where we have it; the eaten date at midnight where we don't.
    Rows written before migration 0006 land in the second case, so history
    still charts — just at eat-date precision instead of vanishing.
    """
    if created_at is not None:
        return created_at
    return datetime.combine(eaten_on, time.min)


def daily_activity(
    db: Session, first_day: date_type, last_day: date_type
) -> tuple[dict[date_type, set[int]], dict[date_type, int]]:
    """({day: active account ids}, {day: meals}) across an inclusive range.

    Bucketing by day happens in Python, not SQL. SQLite has no real date type,
    so func.date() and CAST(x AS DATE) do not agree across the two backends
    this app runs on, and the expression that passes locally is not the one
    that would run live. calls_today set that precedent -- its UTC midnight is
    computed in Python precisely so SQLite and Postgres behave identically. At
    this app's volume the fetched rows number in the thousands, which is
    nothing; if that ever stops being true, the fix is a dialect-aware
    expression, not an untested one.
    """
    window_start = datetime.combine(first_day, time.min)
    active_per_day: dict[date_type, set[int]] = defaultdict(set)
    meals_per_day: dict[date_type, int] = defaultdict(int)

    # `or_` because the two columns answer different questions and either can
    # put a row in the window: a NULL created_at row is only reachable by its
    # date, and a row created recently but backdated far away is only reachable
    # by created_at. Over-fetching slightly is fine — meal_activity_at decides
    # the real day and anything outside the window is dropped below.
    meal_rows = db.execute(
        select(Meal.user_id, Meal.created_at, Meal.date).where(
            or_(Meal.created_at >= window_start, Meal.date >= first_day)
        )
    ).all()
    for user_id, created_at, eaten_on in meal_rows:
        day = meal_activity_at(created_at, eaten_on).date()
        if first_day <= day <= last_day:
            meals_per_day[day] += 1
            active_per_day[day].add(user_id)

    for model in TIMESTAMPED:
        rows = db.execute(
            select(model.user_id, model.created_at).where(
                model.created_at >= window_start
            )
        ).all()
        for user_id, created_at in rows:
            day = created_at.date()
            if first_day <= day <= last_day:
                active_per_day[day].add(user_id)

    return active_per_day, meals_per_day
