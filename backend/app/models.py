from datetime import date as date_type
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    false as sa_false,
    func,
    true as sa_true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naive UTC timestamp — stored identically by SQLite and Postgres."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Tokens issued before this moment are rejected (see auth/deps.py), so
    # changing the password revokes any previously leaked token. Written by
    # both /change-password and /reset-password. Stored with second precision
    # because JWT `iat` is a whole-second claim: change-password mints a fresh
    # token in the same request and it must not read as older than the change.
    password_changed_at: Mapped[datetime | None] = mapped_column(DateTime)


class PasswordReset(Base):
    __tablename__ = "password_resets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    # SHA-256 hex of the emailed token, never the token itself.
    #
    # Not Argon2, deliberately, and this is the opposite of the rule that
    # applies one column up. Argon2 is slow because passwords are low-entropy
    # and guessable offline; this token is 256 bits from secrets.token_urlsafe,
    # so there is no offline guess to slow down and the work factor buys
    # nothing. It would also cost something real: Argon2 salts per hash, so the
    # row could not be found by equality at all — verification would become
    # "load every candidate and hash it", turning an indexed read into a CPU
    # scan that an unauthenticated caller could trigger at will.
    token_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    # Set when the token is spent. Kept rather than deleted: it is the audit
    # trail for "was this link already used?", which is a question support
    # actually gets, and it keeps one code path for every dead token.
    used_at: Mapped[datetime | None] = mapped_column(DateTime)

    # No index on expires_at: the opportunistic purge in auth/router.py plus the
    # global daily send cap keep this table at a few hundred rows, ever.
    __table_args__ = (
        Index("uq_password_resets_token_hash", "token_hash", unique=True),
    )


class Meal(Base):
    __tablename__ = "meals"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # `date` is when the food was EATEN. It is user-chosen and freely
    # backdated, so it says nothing about when the app was used.
    date: Mapped[date_type] = mapped_column(Date)
    # `created_at` is when the row was WRITTEN, which is the actual usage
    # signal: someone logging Thursday-to-Saturday backlog on Sunday used the
    # app on Sunday, and `date` alone would report them active Thu/Fri/Sat and
    # idle Sunday -- backwards, and on every one of those four days.
    #
    # Nullable because rows written before this column existed genuinely have
    # no such record, and inventing one (backfilling from `date`) would be
    # fabricating an observation. NULL means "unknown"; readers fall back to
    # `date` and get eat-date precision for history, real precision after.
    created_at: Mapped[datetime | None] = mapped_column(DateTime, default=utcnow)
    # `updated_at` is when the row was last REWRITTEN, and is null until it is.
    # Null therefore means "no recorded edit" -- either the meal has never been
    # corrected, or it was corrected before this column existed. It is not
    # defaulted to `created_at` on insert: a row that was never edited has no
    # edit time, and stamping one would make every meal look revised. Readers
    # wanting "when did this row last change" take updated_at or created_at,
    # in that order.
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    name: Mapped[str] = mapped_column(String(200))
    calories: Mapped[float] = mapped_column(Float)
    protein: Mapped[float] = mapped_column(Float)
    carbs: Mapped[float | None] = mapped_column(Float)
    fat: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (Index("ix_meals_user_date", "user_id", "date"),)


class MealTemplate(Base):
    """A saved meal the user can re-log in one tap, ingredients included.

    A `Meal` is one flat row, so the ingredient rows someone typed are
    discarded the moment it is saved. Templates are what keep them, which is
    the whole point: re-logging should let you bump the rice from 200 g to
    250 g, not just scale the entire meal proportionally.
    """

    __tablename__ = "meal_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    # The totals, denormalized alongside the items below rather than derived
    # from them. They are what actually gets logged if the user changes
    # nothing, they are computed from the same rows in the same request, and
    # they let the dashboard render a template without parsing JSON.
    calories: Mapped[float] = mapped_column(Float)
    protein: Mapped[float] = mapped_column(Float)
    carbs: Mapped[float | None] = mapped_column(Float)
    fat: Mapped[float | None] = mapped_column(Float)
    # The ingredient rows, as a serialized list[TemplateItem]. JSON rather than
    # a child table because nothing ever queries by ingredient -- this is read
    # whole or not at all, exactly like AIAnalysis.analysis_json. A
    # meal_template_items table would buy a join nobody makes and cost a second
    # CASCADE, a second export shape and a second isolation suite.
    #
    # Nullable: a template saved from the edit-an-existing-meal path has only a
    # single pass-through row, so "no items, just totals" is a valid template
    # and readers must handle it.
    items_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# Case-insensitive template names, unique per user -- the same expression-index
# trick as foods below, and what makes "save as template" an upsert instead of
# a way to accumulate five templates all called "Breakfast".
Index(
    "uq_meal_templates_user_lower_name",
    MealTemplate.user_id,
    func.lower(MealTemplate.name),
    unique=True,
)


class Food(Base):
    __tablename__ = "foods"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(200))
    serving_size: Mapped[float] = mapped_column(Float)
    calories: Mapped[float] = mapped_column(Float)
    protein: Mapped[float] = mapped_column(Float)
    carbs: Mapped[float | None] = mapped_column(Float)
    fat: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str] = mapped_column(String(20), default="user")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (
        CheckConstraint("source IN ('user', 'openfoodfacts')", name="ck_foods_source"),
    )


# Case-insensitive food names, unique per user (replaces v1's global
# UNIQUE COLLATE NOCASE). Expression index works on both SQLite and Postgres.
Index("uq_foods_user_lower_name", Food.user_id, func.lower(Food.name), unique=True)


class WeightEntry(Base):
    __tablename__ = "weights"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    date: Mapped[date_type] = mapped_column(Date)
    # Always kilograms. Pounds are a display preference (settings.weight_unit),
    # converted in the frontend, so stored history stays comparable if the
    # preference changes.
    weight_kg: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # One weigh-in per day: POST /api/weights upserts on this pair, so the
    # constraint is what makes re-logging a date a correction, not a duplicate.
    __table_args__ = (
        Index("uq_weights_user_date", "user_id", "date", unique=True),
    )


class WaterLog(Base):
    """One drink, not one day.

    Deliberately event rows rather than a single running total per date, which
    is the opposite of how `weights` models a day. The difference is undo: a
    mis-tap on "+500" has to be removable, and that is only well defined if the
    row it created still exists. A per-day total would turn undo into a guess
    about which amount to subtract.

    It also means the index below is NOT unique on (user_id, date) -- several
    rows a day is the entire point, where for `weights` a second row for a date
    is a correction.
    """

    __tablename__ = "water_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # The day the water was drunk, user-chosen and freely backdated -- the same
    # meaning `Meal.date` carries, and for the same reason: the dashboard card
    # follows the day being viewed, not the day the button was pressed.
    date: Mapped[date_type] = mapped_column(Date)
    ml: Mapped[float] = mapped_column(Float)
    # When the row was written. Named `created_at` to match every other table
    # here; the roadmap sketch called it `logged_at`, and one table using a
    # different word for the same concept is how a codebase starts needing a
    # glossary. Doubles as the tiebreaker for "which entry was last" when two
    # land on the same date.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    __table_args__ = (Index("ix_water_logs_user_date", "user_id", "date"),)


class StepEntry(Base):
    """One day, not one walk.

    The opposite storage choice from WaterLog, and for the opposite reason.
    Water needs event rows because undo has to remove a *specific* drink; a
    step count is a single figure for the day that gets corrected as the day
    goes on -- read the phone at lunch, read it again at bedtime. There is
    nothing to undo, only a number to replace, so this models a day the way
    `weights` does and takes the same unique constraint.

    Counted in whole steps, so Integer rather than the Float that `weights` and
    `water_logs` use. Those two store measurements, which have fractions;
    8,432.7 steps is not a measurement of anything.
    """

    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # The day walked, user-chosen and freely backdated -- same meaning as
    # `WaterLog.date` and `Meal.date`, so the dashboard card can follow the day
    # being viewed rather than the day the number was typed.
    date: Mapped[date_type] = mapped_column(Date)
    steps: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # One row per day: POST /api/steps upserts on this pair, so re-logging a
    # date is a correction and not a second day's walking.
    __table_args__ = (
        Index("uq_steps_user_date", "user_id", "date", unique=True),
    )


class Supplement(Base):
    """One thing the user takes, and when they mean to take it.

    The schedule is a list of times rather than a count of doses, because the
    reminder half of this feature needs a clock to compare against: "one of your
    two doses is outstanding" is not actionable, "the 08:00 one is overdue" is.
    Times only -- no weekday selection. A second schedule dimension doubles the
    "is this due today" logic everywhere it is asked, and the once-weekly
    supplement it would serve is rare enough to be worth revisiting on evidence
    rather than guessing at now.

    Nothing here contributes calories or macros, deliberately. A protein powder
    that meaningfully feeds a macro total is a meal, and it is logged as one --
    counting it in both places would double it.
    """

    __tablename__ = "supplements"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(100))
    # Free text, and nullable. Supplement doses have no common unit -- IU, mg,
    # µg, ml, capsules, scoops -- so a number plus a unit enum would either be
    # missing whatever someone takes or be a units table nobody asked for. It
    # is displayed beside the name and never computed with.
    dose: Mapped[str | None] = mapped_column(String(60), default=None)
    # The scheduled times, as a serialized list of "HH:MM" strings.
    #
    # The `_json` suffix is load-bearing, exactly as it is on
    # `Setting.water_quick_adds_json`. The API field is `times: list[str]` and
    # a column of the same name would hand Pydantic a JSON *string* for a list
    # field, 500ing every read. Fourth appearance of that trap; the mismatched
    # name is what forces the explicit conversion in routers/supplements.py.
    times_json: Mapped[str] = mapped_column(Text)
    # False means "paused": off the daily card, history intact. Supplements
    # genuinely cycle -- a creatine break, a finished course -- and deleting to
    # declutter would take the check-offs with it. NOT NULL, so it needs both a
    # Python-side default for inserts and a server_default; the table is new,
    # so the latter only ever backfills a downgrade-and-upgrade round trip.
    active: Mapped[bool] = mapped_column(default=True, server_default=sa_true())
    # Also load-bearing rather than metadata: a supplement added today must not
    # make every past day read as a missed dose, so `_day` only schedules it on
    # dates at or after this one. See routers/supplements.py.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# Case-insensitive supplement names, unique per user -- the same expression
# index meal_templates uses. Two rows both called "Magnesium" on a tick list is
# a thing you cannot act on: neither row says which one you already took.
Index(
    "uq_supplements_user_lower_name",
    Supplement.user_id,
    func.lower(Supplement.name),
    unique=True,
)


class SupplementLog(Base):
    """One dose, taken.

    Closest to WaterLog of the three trackers -- several rows a day, each one an
    insert -- but the unique index below is what makes it different: a tick is a
    *state* ("the 08:00 dose is taken"), not an event, so a second tap on the
    same box is the same fact rather than a second dose.

    `time_of_day` stores the literal "08:00", not an index into the
    supplement's times list. An index would silently relabel history the moment
    someone moves their morning dose from 08:00 to 09:00: yesterday's tick would
    re-point at a time it was never taken at. The string keeps the record
    attached to the time it actually happened.

    Named `time_of_day` rather than `time` because `time` is a Postgres keyword.
    SQLAlchemy would quote it correctly; hand-written SQL in a psql session is
    where it would bite, and the keyword buys nothing.
    """

    __tablename__ = "supplement_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Denormalized, even though the owner is reachable through supplement_id.
    # Every isolation query in this app filters on user_id directly, and a join
    # would make this the one table where that pattern does not hold -- which is
    # the table where someone eventually forgets the join.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    supplement_id: Mapped[int] = mapped_column(
        ForeignKey("supplements.id", ondelete="CASCADE")
    )
    # The day the dose was taken, user-chosen and freely backdated -- the same
    # meaning WaterLog.date and StepEntry.date carry.
    date: Mapped[date_type] = mapped_column(Date)
    time_of_day: Mapped[str] = mapped_column(String(5))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)

    # One tick per dose per day: this is what makes POST idempotent rather than
    # a way to record the same pill twice.
    __table_args__ = (
        Index(
            "uq_supplement_logs_user_supp_date_time",
            "user_id",
            "supplement_id",
            "date",
            "time_of_day",
            unique=True,
        ),
    )


class Setting(Base):
    __tablename__ = "settings"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    calorie_goal: Mapped[float] = mapped_column(Float, default=2000)
    protein_goal: Mapped[float] = mapped_column(Float, default=150)
    carbs_goal: Mapped[float] = mapped_column(Float, default=250)
    fat_goal: Mapped[float] = mapped_column(Float, default=70)
    track_carbs: Mapped[bool] = mapped_column(default=False)
    track_fat: Mapped[bool] = mapped_column(default=False)
    # Display unit only — weights are stored in kg regardless.
    weight_unit: Mapped[str] = mapped_column(
        String(2), default="kg", server_default="kg"
    )

    # Body profile. Every field is nullable and the app works with none of it
    # set: the goals above are perfectly usable as hand-typed numbers, which is
    # all they were before this existed.
    height_cm: Mapped[float | None] = mapped_column(Float, default=None)
    # The date, never a stored age. An age column is correct until the user's
    # next birthday and wrong for the following year, and nothing in the system
    # would ever notice it had gone stale.
    birth_date: Mapped[date_type | None] = mapped_column(Date, default=None)
    # Binary, because Mifflin-St Jeor takes a binary term. That is a limitation
    # of the formula rather than a claim about people, and the field is
    # optional. This note used to add that a measured TDEE would replace the
    # formula entirely once there was data; Phase 5 built that, and it turned
    # out to be only half true. Measured TDEE does replace the *activity
    # multiplier*, but BMR is now what bounds a measured value into a
    # believable range -- so the sex term became more load-bearing, not less.
    # The Settings UI says the field is optional, which remains accurate.
    sex: Mapped[str | None] = mapped_column(String(6), default=None)
    activity_level: Mapped[str | None] = mapped_column(String(12), default=None)
    # Signed: negative loses weight, positive gains, zero maintains.
    goal_rate_kg_per_week: Mapped[float | None] = mapped_column(Float, default=None)
    # When true the four goals above are derived from the profile rather than
    # typed, and are rewritten server-side on every settings save and every
    # weigh-in. NOT NULL, so it needs the server_default that backfills the
    # rows which predate it.
    targets_auto: Mapped[bool] = mapped_column(
        default=False, server_default=sa_false()
    )

    # Water. Both nullable, so neither needs a Python-side default nor a
    # server_default: NULL is a meaningful state for each, not a gap to
    # backfill.
    #
    # NULL means "work it out from my weight"; a number means "I set this
    # myself". One nullable column rather than a value plus a `water_goal_auto`
    # boolean, because NULL already carries the flag and two columns could
    # disagree with each other.
    water_goal_ml: Mapped[float | None] = mapped_column(Float, default=None)
    # The quick-add amounts, as a serialized list of ml values. NULL means the
    # shipped defaults, so an account that never opens this setting stores
    # nothing and still gets buttons.
    #
    # The `_json` suffix is load-bearing, not decoration. The API field is a
    # `list[float]` named `water_quick_adds`, and `schemas.Settings` reads
    # attributes off this row directly. A column named `water_quick_adds`
    # holding a *string* would therefore be fed straight into a list field --
    # and every GET /api/settings would 500. The mismatched name forces the
    # explicit conversion in routers/settings.py, exactly as `items_json` does
    # for MealTemplate.items.
    water_quick_adds_json: Mapped[str | None] = mapped_column(Text, default=None)

    # Steps. Nullable like the water pair above, but NULL means something
    # different here and the difference is visible on screen: `water_goal_ml`
    # NULL means "derive it from my weight", where `steps_goal` NULL means "I
    # have no goal". There is no honest derivation for a step target -- 10,000
    # is a 1960s pedometer slogan, not arithmetic on anything about you -- so
    # rather than invent one, the card shows the count with no bar and no
    # percentage until a goal is set.
    steps_goal: Mapped[int | None] = mapped_column(Integer, default=None)

    __table_args__ = (
        CheckConstraint(
            "weight_unit IN ('kg', 'lb')", name="ck_settings_weight_unit"
        ),
        CheckConstraint("sex IN ('male', 'female')", name="ck_settings_sex"),
        CheckConstraint(
            "activity_level IN "
            "('sedentary', 'light', 'moderate', 'active', 'very_active')",
            name="ck_settings_activity_level",
        ),
    )


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    user_text: Mapped[str | None] = mapped_column(Text)
    analysis_json: Mapped[str] = mapped_column(Text)
    meal_id: Mapped[int | None] = mapped_column(
        ForeignKey("meals.id", ondelete="SET NULL")
    )
    # Every row is one billable provider call, which is what the daily caps
    # count. "transcription" rows carry the transcript in user_text and an
    # empty analysis_json; filter on kind == "analysis" when mining this table
    # for corrections to learn from.
    kind: Mapped[str] = mapped_column(
        String(20), default="analysis", server_default="analysis"
    )
