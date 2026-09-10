"""Freeze finished days into daily_stats, so history stops moving.

WHAT THIS IS FOR. See the DailyStat docstring in models.py: /admin derives its
history from live rows, so deleting an account rewrites the past, and a
retention figure built that way is survivorship-biased in the flattering
direction. This module is the writer that makes the past immutable.

TWO INVARIANTS, AND EVERY DECISION BELOW FOLLOWS FROM THEM.

1. **A frozen row is never rewritten.** `_freeze_day` creates a row or leaves
   the existing one exactly as it is. If a re-run could recompute a day, the
   table would be a slower way of deriving from live rows and would inherit the
   bug it exists to fix. The one permitted write to an existing row is a
   cohort maturing from NULL to a number, once, guarded on the NULL.
2. **Today is never frozen.** Today is still changing; a row written at 09:00
   would claim to be the whole day. `ensure_snapshots` fills up to *yesterday*
   and stops.

HOW IT IS TRIGGERED, AND WHY THERE IS NO SCHEDULER.

⚠️ THE OBVIOUS IMPLEMENTATION -- a cron job hitting an endpoint -- IS THE ONE
THAT CANNOT BE USED HERE. The two schedulers this project has both fail:

  * `/api/health` is hit by the cron-job.org keep-warm ping every 10 minutes
    across a 16-hour window AND by Render's own health check roughly every 4
    seconds. app/keep_warm.py spells out what a database touch on that route
    would cost: Neon held awake ~486 h/month, ~122 CU-hours against a 100
    CU-hour free allowance, compute suspended, connections refused. **A
    multi-day outage caused entirely by the monitoring.** Nothing in this
    module may be reachable from that route.
  * GitHub Actions cron delivered **3 of the 114 runs a day** this repo asked
    of it, and backup.yml has started up to 12 h late on consecutive days.

So the trigger is the traffic the app already has. `ensure_snapshots` is
idempotent and cheap when there is nothing to do -- one indexed MAX(date) --
so it rides along on requests that have already opened a database session:
GET /api/admin/stats, and the once-per-day last_seen_at write in auth/deps.py.
Between them, any day on which a single authenticated request happens gets
frozen. A gap is filled by the next call rather than lost.

⚠️ THE HONEST LIMITATION. Backfill computes from live rows AT THE MOMENT IT
RUNS, so a deletion before a day's first freeze still affects that day. Daily
triggering keeps that window to about a day. This table makes history immutable
from the freeze onward; it cannot make it retroactively true.
"""
import logging
from datetime import date as date_type
from datetime import datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .activity import daily_activity
from .models import DailyStat, Meal, User
from .upsert import upsert

logger = logging.getLogger(__name__)

# The retention windows, in days after signup. A cohort from day D is measured
# over [D+1, D+N] -- the signup day itself is excluded, because everyone is
# active on the day they create an account and counting it would make D7 read
# as 100% for anyone who merely finished signing up.
D7 = 7
D30 = 30

# The most days one call will freeze. A first run on an app that has been live
# for months would otherwise scan its whole history in a request that a person
# is waiting on. Anything left over is picked up by the next call, so the only
# consequence of the bound is that a long gap closes over several calls.
MAX_BACKFILL_DAYS = 90


def _first_day_to_freeze(db: Session, last_day: date_type) -> date_type | None:
    """The oldest day with no row yet, or None when there is nothing to do."""
    newest = db.scalar(select(func.max(DailyStat.date)))
    if newest is not None:
        candidate = newest + timedelta(days=1)
    else:
        # Nothing frozen yet: start at the first signup. Starting at the epoch
        # would write thousands of empty rows for days before the app existed.
        first_signup = db.scalar(select(func.min(User.created_at)))
        if first_signup is None:
            return None
        candidate = first_signup.date()
    if candidate > last_day:
        return None
    # Never let one call walk further back than the bound allows.
    return max(candidate, last_day - timedelta(days=MAX_BACKFILL_DAYS - 1))


def _freeze_day(db: Session, day: date_type, values: dict[str, int]) -> None:
    """Insert the row for `day` if it is missing. Never touch an existing one.

    The find-or-create runs inside `upsert` because two requests can arrive in
    the same second -- two tabs, a retry, an admin page load racing an ordinary
    request -- and the unique index on `date` would turn the loser's commit
    into a 500. upsert re-runs this and finds the winner's row instead, which
    is what "already frozen" should do anyway.
    """

    def build() -> DailyStat:
        existing = db.scalar(select(DailyStat).where(DailyStat.date == day))
        if existing is not None:
            # Invariant 1. A frozen day is a historical fact; recomputing it
            # from today's rows is exactly the bug this table exists to fix.
            return existing
        row = DailyStat(date=day, **values)
        db.add(row)
        return row

    upsert(db, build)


def _mature_cohorts(db: Session, last_day: date_type) -> None:
    """Fill cohort_d7/d30_retained for every cohort whose window has closed.

    Runs against live rows on purpose, and this is the asymmetry that makes the
    figure honest: the denominator (`signups`) was frozen the day after the
    cohort formed, while the numerator is counted now. An account that signed
    up and has since deleted is absent here and so counts as NOT retained,
    while still sitting in the denominator. Churn therefore lowers retention,
    which is the whole reason the table exists.
    """
    for window, column in ((D7, "cohort_d7_retained"), (D30, "cohort_d30_retained")):
        attribute = getattr(DailyStat, column)
        due = db.scalars(
            select(DailyStat)
            .where(
                attribute.is_(None),
                # Closed only once the LAST day of the window has fully ended.
                DailyStat.date <= last_day - timedelta(days=window),
                # A cohort of nobody has no retention to measure. Left NULL
                # rather than set to 0, so it never enters the ratio: 0 of 0 is
                # not a retention of zero, it is an absence of evidence.
                DailyStat.signups > 0,
            )
            .order_by(DailyStat.date)
        ).all()
        for row in due:
            setattr(row, column, _retained(db, row.date, window))
        if due:
            db.commit()


def _retained(db: Session, cohort_day: date_type, window: int) -> int:
    """How many accounts created on `cohort_day` came back inside the window."""
    day_start = datetime.combine(cohort_day, time.min)
    day_end = day_start + timedelta(days=1)
    cohort = set(
        db.scalars(
            select(User.id).where(
                User.created_at >= day_start, User.created_at < day_end
            )
        ).all()
    )
    if not cohort:
        return 0
    first = cohort_day + timedelta(days=1)
    last = cohort_day + timedelta(days=window)
    active_per_day, _ = daily_activity(db, first, last)
    seen: set[int] = set()
    for ids in active_per_day.values():
        seen |= ids & cohort
    return len(seen)


def ensure_snapshots(db: Session, today: date_type) -> int:
    """Freeze finished days and mature closed cohorts. Returns days frozen.

    Idempotent, and cheap when there is nothing to do: one indexed MAX(date)
    and, for the cohorts, one indexed lookup per window.
    """
    last_day = today - timedelta(days=1)  # Invariant 2: never today.
    first_day = _first_day_to_freeze(db, last_day)

    frozen = 0
    if first_day is not None:
        active_per_day, meals_per_day = daily_activity(db, first_day, last_day)

        signups_per_day: dict[date_type, int] = {}
        for created_at in db.scalars(
            select(User.created_at).where(
                User.created_at >= datetime.combine(first_day, time.min)
            )
        ).all():
            day = created_at.date()
            if day <= last_day:
                signups_per_day[day] = signups_per_day.get(day, 0) + 1

        day = first_day
        while day <= last_day:
            day_end = datetime.combine(day + timedelta(days=1), time.min)
            _freeze_day(
                db,
                day,
                {
                    "signups": signups_per_day.get(day, 0),
                    "active_users": len(active_per_day.get(day, set())),
                    "meals": meals_per_day.get(day, 0),
                    # Running totals as of the end of the day, counted the same
                    # way the per-day numbers are: a meal belongs to the day it
                    # was eaten, an account to the day it was created.
                    "total_users": db.scalar(
                        select(func.count())
                        .select_from(User)
                        .where(User.created_at < day_end)
                    )
                    or 0,
                    "total_meals": db.scalar(
                        select(func.count())
                        .select_from(Meal)
                        .where(Meal.date <= day)
                    )
                    or 0,
                },
            )
            frozen += 1
            day += timedelta(days=1)

    _mature_cohorts(db, last_day)
    return frozen


def ensure_snapshots_quietly(db: Session, today: date_type) -> None:
    """ensure_snapshots, but a failure here can never fail the caller.

    ⚠️ This is the form auth/deps.py uses, and the guard is not decoration.
    That call site sits inside get_current_user, so an exception raised there
    would 500 **every authenticated request in the app** -- the dashboard, the
    log form, everything -- because a metrics table could not be written.
    A missing snapshot row is a gap in a chart; an unhandled one would be an
    outage. The rollback matters as much as the except: Postgres aborts the
    whole transaction on error, so without it the caller's own session would be
    poisoned and its next query would fail instead.
    """
    try:
        ensure_snapshots(db, today)
    except Exception:
        db.rollback()
        logger.exception("daily_stats snapshot failed")
