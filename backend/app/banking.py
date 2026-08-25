"""Calorie banking: moving calories between days without moving the week.

The arithmetic only. No database, no request, no `today` of its own -- every
function takes what it needs, so all of it is testable without a fixture, the
way `calculations.py` is.

Two things happen here, and they are not the same thing:

  * **Planning ahead.** A dinner on Saturday funded by four smaller days around
    it. The group's deltas sum to *zero*: every calorie the big day gains is a
    calorie some other day gives up, and both the giver and the taker are rows.

  * **Compensating after.** A Saturday that already ran over, spread across the
    days ahead. The deltas share one sign and sum to the *negation of the
    surplus*, because the balancing entry is not a row at all -- it is the meals
    already logged on the event day. A past-dated row written to "balance the
    ledger" would look, to every date-keyed reader in this app, like a target
    adjustment on a day that is already finished.

That asymmetry is the reason `kind` is stored rather than derived. Both rules
are checkable only at write time, when `today` and the measured surplus are
known; neither can be re-derived from the table afterwards.

**What this module refuses to do: clamp.** Everywhere else in the app a clamp is
the server correcting a number it derived itself, and explaining that it did.
Here the numbers are the user's. Quietly turning their plan into a different
plan and calling it theirs is exactly the false precision the rest of the app is
built to avoid, so a plan that breaches a floor *fails*, naming the day and the
reason, and nothing is written.

A last honesty note, for the caller rather than for this module: none of this
creates a calorie debt the app will collect. Measured TDEE is fitted from mean
intake against the weight trend, so one large day is already absorbed as a
slightly slower week. Redistribution leaves that mean alone, which is the whole
reason the sums above have to hold.
"""
from collections.abc import Sequence
from datetime import date as date_type
from typing import NamedTuple

from .calculations import (
    FAT_FRACTION_OF_CALORIES,
    KCAL_PER_G_CARB,
    KCAL_PER_G_FAT,
    KCAL_PER_G_PROTEIN,
    MIN_TARGET_FRACTION_OF_TDEE,
    MIN_TARGET_KCAL,
)

# The two kinds, spelled once. The CHECK constraint on the table repeats these
# strings; nothing else should.
KIND_PLANNED = "planned"
KIND_COMPENSATING = "compensating"
KINDS = (KIND_PLANNED, KIND_COMPENSATING)

# POLICY. Refusals, not science.
#
# Fourteen days is a plan; beyond that it is a diet, and a diet belongs in the
# calorie goal itself where the TDEE machinery can see it. 3000 kcal on a single
# day is a stray-digit catcher and nothing more -- it carries no opinion about
# how much anyone should eat, it only stops a misplaced zero from silently
# becoming a target.
MAX_PLAN_DAYS = 14
MAX_DAY_DELTA_KCAL = 3000.0

# Deltas are whole kcal by construction (`split_delta` rounds), but a
# hand-written request need not be, so the sum rules compare with a tolerance
# rather than for exact equality. Half a kcal is far below anything meaningful
# and far above float drift over fourteen additions.
SUM_TOLERANCE_KCAL = 0.5


class DayGoals(NamedTuple):
    """The four numbers a day's rings are drawn against."""

    calories: float
    protein: float
    carbs: float
    fat: float


class PlanEntry(NamedTuple):
    """One adjusted day: the date, and the signed calories moved onto it."""

    date: date_type
    calorie_delta: float


class PlanCheck(NamedTuple):
    """Whether a plan may be written, and what could not be checked.

    `refusals` empty means the plan is allowed. It is a list rather than a
    single string because a plan is validated as a *set*: four days can each
    breach the floor, and reporting only the first sends the user round the loop
    four times.

    `unchecked` is not a refusal and not a warning about the plan -- it names a
    floor that could not be evaluated at all, so the caller can say so on screen
    instead of letting a plan look fully vetted when half the vetting was
    skipped.
    """

    refusals: list[str]
    unchecked: str | None


def split_delta(total_kcal: float, day_count: int) -> list[float]:
    """Divide calories across days so the parts sum to exactly the whole.

    Whole kcal per day, with the remainder handed out one at a time to the
    earliest days. The parts are guaranteed to re-add to the rounded total,
    which is what lets the sum rules above be an equality rather than an
    approximation -- splitting 100 over 3 days as 33.33 each and then asserting
    the group sums to zero would fail on a rounding error the user never made.

    Sign is carried, not inferred: divmod on the magnitude and the sign applied
    afterwards, because Python's floor division rounds toward negative infinity
    and would otherwise split -100 into three parts of -34 summing to -102.
    """
    if day_count < 1:
        raise ValueError("split_delta needs at least one day")

    total = int(round(total_kcal))
    sign = 1 if total >= 0 else -1
    base, remainder = divmod(abs(total), day_count)
    return [float(sign * (base + (1 if i < remainder else 0))) for i in range(day_count)]


def apply_delta(
    goals: DayGoals,
    delta: float,
    fat_fraction: float = FAT_FRACTION_OF_CALORIES,
) -> DayGoals:
    """Move `delta` calories onto a day's targets. Protein does not move.

    Protein is derived from body weight, not from the calorie budget -- that is
    the whole reason `calculations.macro_targets` is ordered the way it is. On a
    shaved day protein matters *more*, not less, so shaving it is backwards.
    Carbohydrate and fat absorb the difference on the same 25/75 split that
    function uses.

    The two macros are moved *additively* rather than recomputed from the new
    calorie total. This matters: with `targets_auto` off the four goal columns
    are set independently and need not add up to each other, and recomputing
    carbs as "whatever is left" would quietly rewrite a manual split the user
    chose into one they did not. Moving only the delta preserves whatever
    relationship their goals already had.

    Both macros floor at zero, and when one does the split no longer accounts
    for the full delta -- the same caveat `macro_targets` carries, for the same
    reason. Calories floor at zero too; a plan that gets anywhere near it will
    have been refused by the floor check long before.
    """
    fat_kcal = fat_fraction * delta
    carb_kcal = delta - fat_kcal

    return DayGoals(
        calories=max(goals.calories + delta, 0.0),
        protein=goals.protein,
        carbs=max(goals.carbs + carb_kcal / KCAL_PER_G_CARB, 0.0),
        fat=max(goals.fat + fat_kcal / KCAL_PER_G_FAT, 0.0),
    )


def macro_kcal(goals: DayGoals) -> float:
    """What the three macros actually add up to, in calories.

    Exists so a caller can see the gap `apply_delta` warns about instead of
    assuming there is none.
    """
    return (
        goals.protein * KCAL_PER_G_PROTEIN
        + goals.carbs * KCAL_PER_G_CARB
        + goals.fat * KCAL_PER_G_FAT
    )


def check_floor(
    calories: float,
    sex: str | None,
    tdee: float | None,
    min_kcal: dict[str, float] = MIN_TARGET_KCAL,
    min_fraction: float = MIN_TARGET_FRACTION_OF_TDEE,
) -> tuple[float, str | None]:
    """The lowest a day may be shaved to, and which floor could not be applied.

    The same two floors `calculations.target_calories` uses, and deliberately
    not a third: a day inside a plan is held to exactly the standard a permanent
    target is, because the body cannot tell the difference between a low day
    that was planned and a low day that was not.

    Both floors can be missing, independently, and the rule is to apply every
    one that can be evaluated rather than to skip the check:

      * No `sex` -- fall back to the lower of the absolute floors, which is what
        `target_calories` already does for an unrecognised value. A floor that
        is too permissive for this person still beats no floor.
      * No `tdee` -- there is no proportional floor to compute. This is the one
        worth reporting: it is the floor that binds for a large person, for whom
        1200 kcal is nowhere near a real limit, and it is absent exactly when
        the body profile is incomplete.

    Returns the floor and, when one was skipped, prose saying so. Note that a
    missing `sex` implies a missing `tdee` in practice -- `compute_targets`
    lists `sex` among its `missing` fields, so an incomplete profile yields no
    measured expenditure either -- but they are checked separately here so that
    neither depends on the other staying true.
    """
    floor = min_kcal.get(sex or "", min(min_kcal.values()))
    if tdee is None:
        return floor, (
            f"Only the absolute {round(floor):g} kcal floor was checked. The "
            f"proportional one needs your estimated daily expenditure, which "
            f"needs a complete body profile — so on a plan this large it may be "
            f"lower than it should be."
        )
    return max(floor, tdee * min_fraction), None


def validate_plan(
    entries: Sequence[PlanEntry],
    *,
    kind: str,
    event_date: date_type,
    today: date_type,
    goals: DayGoals,
    sex: str | None,
    tdee: float | None,
    surplus_kcal: float | None = None,
) -> PlanCheck:
    """Check a whole plan at once. Empty `refusals` means it may be written.

    Validated as a set rather than field by field, which is why this is not a
    Pydantic validator: no per-field rule can see that four days sum to zero, or
    that the event day is missing from its own group.

    `surplus_kcal` is how far over target the event day ran -- positive for
    over-eaten, negative for under. Required for `compensating` and meaningless
    for `planned`.
    """
    refusals: list[str] = []

    if kind not in KINDS:
        # Programmer error, not user error: the schema constrains this before
        # anything reaches here.
        raise ValueError(f"unknown plan kind {kind!r}")

    if not entries:
        return PlanCheck(refusals=["A plan needs at least one day to adjust."], unchecked=None)

    if len(entries) > MAX_PLAN_DAYS:
        refusals.append(
            f"A plan can cover at most {MAX_PLAN_DAYS} days; this one covers "
            f"{len(entries)}. Spreading further than a fortnight is a change to "
            f"your calorie goal, not a plan around one day."
        )

    dates = [entry.date for entry in entries]
    duplicates = sorted({d for d in dates if dates.count(d) > 1})
    for day in duplicates:
        refusals.append(f"{day.isoformat()} appears twice in this plan.")

    # Every *adjusted* day is today or later. A past day may be the source of
    # the number -- that is exactly what `compensating` is -- but rewriting the
    # target of a day whose meals are already logged changes what the user was
    # measured against after the fact, which is not an adjustment, it is
    # revisionism.
    for day in sorted(set(dates)):
        if day < today:
            refusals.append(
                f"{day.isoformat()} has already happened, so its target cannot "
                f"be changed. Only today and later can be adjusted."
            )

    for entry in entries:
        if abs(entry.calorie_delta) > MAX_DAY_DELTA_KCAL:
            refusals.append(
                f"{entry.date.isoformat()} moves by "
                f"{round(entry.calorie_delta):+g} kcal, past the "
                f"{round(MAX_DAY_DELTA_KCAL):g} kcal limit for a single day."
            )

    refusals.extend(
        _check_sums(entries, kind=kind, event_date=event_date,
                    today=today, surplus_kcal=surplus_kcal)
    )

    floor, unchecked = check_floor(goals.calories, sex, tdee)
    for entry in entries:
        adjusted = apply_delta(goals, entry.calorie_delta)
        if adjusted.calories < floor:
            refusals.append(
                f"{entry.date.isoformat()} would drop to "
                f"{round(adjusted.calories):g} kcal, below the "
                f"{round(floor):g} kcal floor. Spread this over more days, or "
                f"over a smaller total."
            )

    return PlanCheck(refusals=refusals, unchecked=unchecked)


def _check_sums(
    entries: Sequence[PlanEntry],
    *,
    kind: str,
    event_date: date_type,
    today: date_type,
    surplus_kcal: float | None,
) -> list[str]:
    """The zero-sum rule, which is two different rules. See the module docstring.

    Split out because it is the part a later refactor would flatten into one
    branch, and because the two halves share no code at all -- only a name.
    """
    refusals: list[str] = []
    dates = {entry.date for entry in entries}
    total = sum(entry.calorie_delta for entry in entries)

    if kind == KIND_PLANNED:
        # The event day is itself adjusted, so it is one of these rows, and the
        # group closes on itself.
        if event_date not in dates:
            refusals.append(
                f"The day being planned for ({event_date.isoformat()}) is not "
                f"one of the days being adjusted."
            )
        if abs(total) > SUM_TOLERANCE_KCAL:
            refusals.append(
                f"These days do not balance: they add {round(total):+g} kcal to "
                f"the week. A planned day has to be funded by the others, or the "
                f"plan is a change to your calorie goal wearing a different name."
            )
        return refusals

    # KIND_COMPENSATING. The event day is already logged and is not a row; the
    # meals on it are the other side of the ledger.
    if event_date in dates:
        refusals.append(
            f"{event_date.isoformat()} is the day being compensated for, so it "
            f"cannot also be one of the days absorbing it."
        )
    if event_date > today:
        refusals.append(
            f"{event_date.isoformat()} has not happened yet, so there is nothing "
            f"to compensate for. Plan it ahead instead."
        )
    if surplus_kcal is None:
        raise ValueError("compensating plans need the surplus they are spreading")

    if abs(total + surplus_kcal) > SUM_TOLERANCE_KCAL:
        refusals.append(
            f"These days move {round(total):+g} kcal, which does not offset the "
            f"{round(surplus_kcal):+g} kcal difference on "
            f"{event_date.isoformat()}."
        )

    # One sign. A "compensation" containing both a raise and a shave is two
    # plans, and cancelling it would undo an intention the user never expressed
    # as one.
    signs = {1 if entry.calorie_delta > 0 else -1 for entry in entries
             if entry.calorie_delta != 0}
    if len(signs) > 1:
        refusals.append(
            "Some of these days go up and others go down. Compensating moves "
            "every day the same way."
        )
    return refusals
