"""Operator metrics: how many people use this app, and how much.

PRIVACY BOUNDARY — read this before adding a field.

Every other router here is scoped to the authenticated user. This one
deliberately is not, which is exactly why it is the only router behind
`require_admin`. What it may expose is **counts, dates and account
identifiers**: email, signup date, last-active, and how many meals, weigh-ins,
foods, saved meal templates, water logs, step-count days, supplements, doses
ticked and banked calorie days each account has.

Admins do **not** see meal names, weight values, food entries, meal-template
names, **supplement names or doses**, how much anyone drank or walked,
**which days a calorie plan covers**, or voice-note transcripts. Two of those
matter more than the rest. A supplement list can name a prescription, which
makes it the most disclosive data this app stores. A plan's `event_date` is
disclosive in a different way -- it does not describe health at all, it
describes a life: it says this person has something on the 5th. Counts say
everything an operator needs while saying neither. That is what keeps README.md's "every API endpoint is scoped to the
authenticated user" and the Settings privacy copy true without a rewrite.
`tests/test_admin.py` asserts the absence positively, so a later "just one
useful field" commit fails a test rather than quietly failing the promise.

If per-user drill-down is ever wanted, it goes behind a consent toggle the user
themselves flips — never an admin override. This is the kind of constraint that
erodes one convenient field at a time, which is why it is written down here
rather than remembered.
"""
import math
from collections import defaultdict
from datetime import date as date_type
from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..activity import TIMESTAMPED, daily_activity
from ..auth.deps import require_admin
from ..db import get_db
from ..keep_warm import (
    COLD_START_SUSPECT_S,
    WINDOW_TZ,
    in_window_at,
    snapshot,
    window_tz,
)
from ..models import (
    AIAnalysis,
    CaloriePlanDay,
    DailyStat,
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
from ..snapshots import D7, D30, ensure_snapshots
from ..schemas import (
    Activation,
    AdminDailyActivity,
    AdminDailyCount,
    AdminStats,
    AILatency,
    AdminUserRow,
    KeepWarmStatus,
    Retention,
    SignupHours,
    TimeToFirstMeal,
)
from .ai import calls_today, global_daily_limit

router = APIRouter(prefix="/api/admin", tags=["admin"])

# The chart width, and the "is anyone here this week" window inside it. Both
# are whole UTC days, matching the boundary calls_today already uses — mixing
# a local-day window with a UTC-day counter on the same screen is how two
# numbers that should agree stop agreeing.
CHART_DAYS = 30
# The global cap is 500 calls/day by default, so a 30-day window has a hard
# ceiling around 15,000 rows. This bounds the fetch under that and degrades to
# "the most recent N timed calls" rather than to a wrong answer.
LATENCY_SAMPLE_LIMIT = 10_000
ACTIVE_WINDOW_DAYS = 7

# What one Gemini call costs, in US dollars. A committed constant rather than a
# setting: it is an estimate from the roadmap's unit-economics work (~$0.01 per
# meal analysis), it changes only when the provider's pricing does, and a value
# that looks configurable while governing nothing is worse than one you have to
# edit. ⚠️ Every row in ai_analyses is one billable call, transcriptions
# included -- that is what makes multiplying by a row count honest.
AI_CALL_COST_USD = 0.01


def _percentile(sorted_values: list[int], q: float) -> int:
    """Nearest-rank percentile -- always a value that actually occurred.

    statistics.quantiles interpolates, which invents a duration nobody ever
    waited, and with a handful of samples it does so most of the time. Every
    figure on this page is meant to be something that happened. It is the same
    rule useWakeProgress states when it takes the MEDIAN of ten cold starts and
    refuses the mean, because no boot ever took the mean.
    """
    if not sorted_values:
        return 0
    rank = max(1, math.ceil(q * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]

# No rate limiting, per rate_limit.py's rule: only the auth endpoints are
# limited, because everything else already requires a valid token — and this
# one additionally requires being on the allowlist.


def _activation(db: Session, total_users: int) -> Activation:
    """How far accounts get, not how many exist.

    The number this app most needed and did not have. On 2026-09-08 three
    strangers had signed up and none had written a single row, and there was no
    figure anywhere that said so -- it had to be read off a table of accounts by
    eye. "Signed up" is not a funnel; "signed up, logged once, came back and
    logged again" is.

    Two steps rather than one because they fail for different reasons. Never
    logging a meal is an onboarding failure -- the person never understood what
    to do or never got far enough to try. Logging on exactly one day is a
    retention failure: they did the thing once and it was not worth repeating.
    """
    with_meal = db.scalar(
        select(func.count(func.distinct(Meal.user_id)))
    ) or 0
    # Distinct DAYS, not distinct meals: three meals on one Tuesday is one
    # session with a good appetite, not a habit.
    per_user_days = db.execute(
        select(Meal.user_id, func.count(func.distinct(Meal.date)))
        .group_by(Meal.user_id)
    ).all()
    on_two_days = sum(1 for _, day_count in per_user_days if day_count >= 2)
    return Activation(
        total_users=total_users,
        logged_a_meal=with_meal,
        logged_on_two_days=on_two_days,
    )


def _time_to_first_meal(db: Session) -> TimeToFirstMeal:
    """Median and p90 hours from signing up to logging the first meal.

    Separates "left immediately" from "started slowly", which look identical in
    an activation percentage and want opposite responses: the first is a
    first-run problem, the second is a reason to be patient.

    Only accounts that HAVE logged a meal are in here. Including the ones that
    never did -- as an infinity, or as time-since-signup -- would make the
    median a statement about how long the app has been live.
    """
    first_meal = (
        select(Meal.user_id, func.min(Meal.created_at).label("first_at"))
        .where(Meal.created_at.is_not(None))
        .group_by(Meal.user_id)
        .subquery()
    )
    rows = db.execute(
        select(User.created_at, first_meal.c.first_at)
        .join(first_meal, first_meal.c.user_id == User.id)
    ).all()
    hours = sorted(
        max(0, int((first_at - created_at).total_seconds() // 3600))
        for created_at, first_at in rows
        if first_at is not None and first_at >= created_at
    )
    return TimeToFirstMeal(
        count=len(hours),
        median_hours=_percentile(hours, 0.5),
        p90_hours=_percentile(hours, 0.9),
    )


def _signup_hours(db: Session) -> SignupHours:
    """When accounts are created, in the keep-warm window's own timezone.

    ⚠️ The point is not a body-clock chart, it is the cold start. Render's free
    instance sleeps outside 05:00-21:00 Asia/Dubai, so a signup at 02:00 met a
    52 s boot and one at noon did not -- and "was the cold start what lost
    them" has been an open question since the first real signups, answerable
    only from this column. Local hours rather than UTC because the window is
    defined in local hours; a UTC histogram would have to be re-read against
    the offset every time anyone looked at it.
    """
    tz = window_tz()
    by_hour = [0] * 24
    outside = 0
    for created_at in db.scalars(select(User.created_at)).all():
        # Stored naive-UTC (models.utcnow), so it must be told it is UTC before
        # it can be converted -- otherwise astimezone would read it as local
        # server time, which is UTC on Render today and a silent four-hour
        # error the day it is not.
        local = created_at.replace(tzinfo=timezone.utc).astimezone(tz)
        by_hour[local.hour] += 1
        if not in_window_at(local):
            outside += 1
    return SignupHours(timezone=WINDOW_TZ, by_hour=by_hour, outside_window=outside)


def _feature_adoption(db: Session) -> dict[str, int]:
    """Accounts that have EVER used each feature.

    Ever, not recently: this answers "is anyone using this at all", which is a
    question about whether a feature earns its place in the UI. Distinct
    accounts, so one enthusiast cannot make a feature look adopted.

    Worth as much for what it says to CUT as for what it says to build -- the
    dashboard declutter was argued from screenshots, and this is the version of
    that argument with numbers behind it.
    """
    sources = {
        "meals": Meal,
        "weights": WeightEntry,
        "foods": Food,
        "meal_templates": MealTemplate,
        "water": WaterLog,
        "steps": StepEntry,
        "supplements": SupplementLog,
        "calorie_plans": CaloriePlanDay,
        "ai": AIAnalysis,
    }
    return {
        name: db.scalar(select(func.count(func.distinct(model.user_id)))) or 0
        for name, model in sources.items()
    }


def _retention(db: Session) -> Retention:
    """D7/D30 from frozen cohorts only -- the one figure that must not derive.

    Summed across matured cohorts rather than averaged across them: a week with
    one signup and a week with fifty are not equally strong evidence, and
    averaging the two ratios would treat them as if they were.

    A cohort still inside its window contributes NOTHING, not a zero. Counting
    an unfinished cohort would make retention appear to collapse every time
    somebody new signed up, which is the opposite of what the number means.
    """
    def summed(column) -> tuple[int, int, int]:
        row = db.execute(
            select(
                func.coalesce(func.sum(DailyStat.signups), 0),
                func.coalesce(func.sum(column), 0),
                func.count(),
            ).where(column.is_not(None))
        ).one()
        return int(row[0]), int(row[1]), int(row[2])

    d7_size, d7_kept, d7_cohorts = summed(DailyStat.cohort_d7_retained)
    d30_size, d30_kept, d30_cohorts = summed(DailyStat.cohort_d30_retained)
    return Retention(
        d7_window_days=D7,
        d30_window_days=D30,
        d7_cohort_size=d7_size,
        d7_retained=d7_kept,
        d7_cohorts=d7_cohorts,
        d30_cohort_size=d30_size,
        d30_retained=d30_kept,
        d30_cohorts=d30_cohorts,
    )

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

    ⚠️ THIS IS "LAST WROTE SOMETHING", NOT "LAST HERE", and the difference is
    the point of the column beside it. Derived from rows the account created,
    so a session spent reading the dashboard and logging nothing leaves no
    trace here at all. `users.last_seen_at` is the other half: written once a
    UTC day by auth/deps.py, it says the account was present. Read together,
    `seen but never active` is an onboarding failure and `neither` is a bounce
    -- opposite problems, and until 2026-09-10 this app could not tell them
    apart, which is exactly the ambiguity the first three real signups landed
    in.

    This docstring used to reject a `last_seen` column on the grounds that
    keeping it accurate "means a write on every authenticated request". True at
    timestamp precision. **False at date precision**, which is what shipped:
    at most one UPDATE per account per day, and nothing reads below the day.

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

    for model in TIMESTAMPED:
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
    """Per-account metrics, newest signups first.

    `last_active_at` and `last_seen_at` are deliberately BOTH here. One says
    when the account last wrote something, the other when it was last present
    at all; the pair is what turns "signed up and did nothing" from a dead end
    into a diagnosis. See _last_active_by_user.
    """
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
    calorie_plan_days = _count_by_user(db, CaloriePlanDay, ids)
    last_active = _last_active_by_user(db, ids)

    return [
        AdminUserRow(
            id=u.id,
            email=u.email,
            created_at=u.created_at,
            last_active_at=last_active.get(u.id),
            last_seen_at=u.last_seen_at,
            meals=meals.get(u.id, 0),
            weights=weights.get(u.id, 0),
            foods=foods.get(u.id, 0),
            meal_templates=templates.get(u.id, 0),
            ai_calls=ai_calls.get(u.id, 0),
            water_logs=water_logs.get(u.id, 0),
            steps=steps.get(u.id, 0),
            supplements=supplements.get(u.id, 0),
            supplement_logs=supplement_logs.get(u.id, 0),
            calorie_plan_days=calorie_plan_days.get(u.id, 0),
        )
        for u in users
    ]


@router.get("/stats", response_model=AdminStats)
def stats(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    """App-wide totals, the two charted series, and the funnel figures.

    ⚠️ The series here are DERIVED FROM LIVE ROWS and therefore move when an
    account is deleted -- see the DailyStat docstring. That is acceptable for a
    30-day chart and NOT acceptable for retention, which is why `retention`
    below is read from frozen snapshot rows and everything else is not.
    """
    today = datetime.now(timezone.utc).date()

    # Bring frozen history up to date while an admin is looking at it. Cheap
    # when there is nothing to do, and this is one of only two triggers -- see
    # app/snapshots.py for why neither /api/health nor a cron can be the other.
    ensure_snapshots(db, today)

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

    # app/activity.py, not an expression here: daily_stats freezes the same
    # figure, and a chart that disagreed with the frozen history about what
    # "active" means would leave no way to tell which of the two was right.
    active_per_day, meals_per_day = daily_activity(db, first_day, today)

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

    # Only rows that carry a timing; NULL means "never measured", which is not
    # the same as fast and must not enter a percentile. Newest first so the
    # limit above drops the oldest samples rather than an arbitrary slice.
    timing_rows = db.execute(
        select(AIAnalysis.kind, AIAnalysis.provider_ms, AIAnalysis.server_uptime_s)
        .where(
            AIAnalysis.created_at >= window_start,
            AIAnalysis.provider_ms.is_not(None),
        )
        .order_by(AIAnalysis.created_at.desc())
        .limit(LATENCY_SAMPLE_LIMIT)
    ).all()

    calls_by_kind = {kind: count for kind, count in ai_by_kind}
    samples: dict[str, list[int]] = defaultdict(list)
    cold_server_calls = 0
    for kind, provider_ms, server_uptime_s in timing_rows:
        samples[kind].append(provider_ms)
        # Uptime shorter than the window a fresh boot occupies. Ambiguous in
        # exactly the way the keep-warm verdict is -- a deploy also restarts the
        # process -- which is why this is a count to compare against, not a
        # verdict on its own.
        if server_uptime_s is not None and server_uptime_s < COLD_START_SUSPECT_S:
            cold_server_calls += 1

    latency_by_kind = {}
    for kind, values in samples.items():
        values.sort()
        latency_by_kind[kind] = AILatency(
            calls=calls_by_kind.get(kind, len(values)),
            count=len(values),
            p50_ms=_percentile(values, 0.5),
            p95_ms=_percentile(values, 0.95),
        )

    ai_calls_30d = sum(calls_by_kind.values())

    return AdminStats(
        total_users=total_users,
        total_meals=total_meals,
        activation=_activation(db, total_users or 0),
        time_to_first_meal=_time_to_first_meal(db),
        signup_hours=_signup_hours(db),
        feature_adoption=_feature_adoption(db),
        retention=_retention(db),
        ai_spend_30d_usd=round(ai_calls_30d * AI_CALL_COST_USD, 2),
        # Per ACTIVE account, not per account. Dividing by every account ever
        # created would make the figure fall every time somebody signed up and
        # left, which is the direction that flatters and the opposite of what a
        # cost-per-user number is for: G3 has to price against the people who
        # actually use it.
        ai_spend_30d_usd_per_active=round(
            ai_calls_30d * AI_CALL_COST_USD / max(1, distinct_active(days)), 2
        ),
        signups_7d=sum(signups_per_day.get(day, 0) for day in recent),
        signups_30d=sum(signups_per_day.get(day, 0) for day in days),
        active_7d=distinct_active(recent),
        active_30d=distinct_active(days),
        meals_7d=sum(meals_per_day.get(day, 0) for day in recent),
        ai_calls_today=calls_today(db),
        ai_global_daily_limit=global_daily_limit(),
        ai_calls_30d_by_kind=calls_by_kind,
        ai_latency_30d_by_kind=latency_by_kind,
        ai_calls_30d_on_cold_server=cold_server_calls,
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


@router.get("/keep-warm", response_model=KeepWarmStatus)
def keep_warm(admin: User = Depends(require_admin)):
    """Is the cold start actually being kept away, and by what.

    No `db` parameter: everything reported here lives in this process's memory,
    and the only database touch in the whole request is require_admin resolving
    the caller. That is not an optimisation -- see app/keep_warm.py for why the
    persisted version of this panel is the one that takes Neon down.

    Inside the metrics-only boundary this module's docstring defines. It
    describes the server, not any account, so there is nothing here to scope.
    """
    return snapshot()
