from datetime import date as date_type
from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    func,
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
    date: Mapped[date_type] = mapped_column(Date)
    name: Mapped[str] = mapped_column(String(200))
    calories: Mapped[float] = mapped_column(Float)
    protein: Mapped[float] = mapped_column(Float)
    carbs: Mapped[float | None] = mapped_column(Float)
    fat: Mapped[float | None] = mapped_column(Float)

    __table_args__ = (Index("ix_meals_user_date", "user_id", "date"),)


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

    __table_args__ = (
        CheckConstraint(
            "weight_unit IN ('kg', 'lb')", name="ck_settings_weight_unit"
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
