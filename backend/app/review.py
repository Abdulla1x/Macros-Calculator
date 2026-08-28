"""The weekly review: what a week of logs says, and what it refuses to say.

The arithmetic only. No database, no request, no `now` of its own -- every
function takes what it needs, so all of it is testable without a fixture, the
way `calculations.py` and `calibration.py` are.

**The rule this module exists to keep: it reports, it never prescribes.**

That is not a stylistic preference, it is the whole reason this feature is
shaped the way it is. Every safety guarantee in this app is a clamp on a
computed number -- `MAX_GOAL_RATE_KG_PER_WEEK`, `MIN_TARGET_KCAL`,
`MIN_TARGET_FRACTION_OF_TDEE`, `clamp_measured_tdee` -- and **there is no clamp
on prose**. A review that told someone what to eat would route around all of it
in one sentence. So no string built here may contain a recommended intake, rate
or target: every number in every sentence is one the app already computed *and*
already clamped, and `status` compares the user's figure to **the user's own
stated goal**, never to an opinion this module holds.

Three further things carry the design:

  * **"Weekly" is when it is published, not the window every number uses.** The
    intake, protein and tracker checks are about the last seven complete days.
    The weight check is not, and cannot be: a seven-day weight slope is exactly
    the noise `TDEE_MIN_SPAN_DAYS` was chosen against -- `calculations.py`
    records that a 7-day window produced 2700 kcal against 2498 from the
    formula because trend weight had moved -0.01 kg. So the rate check reuses
    `weekly_rate`'s own 28-day window and **says so in its sentence**. Every
    check carries `sample_days`, and no check may describe a window it did not
    use.

  * **The window ends yesterday.** Today is a part-logged day -- breakfast in,
    dinner not -- and averaging it in understates intake, which would make
    every review read as a better week than it was. `targets._measure_tdee`
    and the dashboard's seven-day trend already stop at yesterday for the same
    reason and in nearly the same words.

  * **A check that does not apply is absent, not empty.** A section is built
    only when the user has already told the app they use that thing -- a steps
    goal exists, water has been logged, the profile is complete. Nothing here
    invents a target nobody set, and nothing renders a row of dashes at someone
    for a tracker they deliberately ignore.

What this module refuses to do, following `calibration.py`: report a comparison
it cannot support. A check that cannot answer still returns its counts -- they
are the useful part of a refusal -- with `status` "unknown" and a sentence in
`unavailable_reason` naming what is missing. "You are three weigh-ins away from
an answer" beats a confident number built on four.
"""
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date as date_type
from typing import NamedTuple

from .calculations import RATE_MIN_POINTS, RATE_WINDOW_DAYS
from .calibration import CalibrationSummary

# CONVENTION. Seven complete days. Not a statistical choice -- it is the period
# people already think in, and it matches the dashboard's own trend window so
# the two cannot disagree about what "this week" covered.
REVIEW_WINDOW_DAYS = 7

# POLICY. How many of the seven days have to carry a meal before the figures
# below are worth reading as a description of the week.
#
# Five is a refusal threshold, not a target: at four or fewer, a "daily average"
# is an average of a minority of the week and the days missing from it are
# likelier to be the unusual ones -- nobody forgets to log a quiet Tuesday and
# remembers a birthday. The averages are still shown below this line, because
# they are true about the days they cover; what changes is that the logging
# check says so first, and every other sentence names its own denominator.
LOGGING_DENSE_DAYS = 5

# POLICY. How far a weekly average may sit from the target and still read as
# "on track", as a fraction of the target.
#
# Five per cent of a 2000 kcal target is 100 kcal a day, which is smaller than
# the error in estimating a single restaurant meal -- so a band narrower than
# this would flag ordinary measurement noise as a miss, every week, and train
# the reader to ignore the check. It is a presentation threshold and nothing
# else: no target moves because of it.
INTAKE_TOLERANCE_FRACTION = 0.05

# POLICY. What share of logged days have to reach the protein goal before
# protein reads as "on track". Two thirds is a judgement about consistency
# rather than about nutrition -- the goal itself is the nutritional claim, and
# it is set in calculations.py at PROTEIN_G_PER_KG.
PROTEIN_HIT_FRACTION = 2 / 3

# POLICY. Same idea for the daily trackers, and deliberately looser. Water and
# steps are habit counters with no downstream consequence -- nothing derives a
# target from them -- so the bar for "you are doing this" is lower than for a
# macro that feeds the energy balance.
TRACKER_HIT_FRACTION = 0.5

# POLICY. How close the measured weekly rate has to sit to the goal rate, in
# kg/week, before the two read as agreeing.
#
# 0.15 kg/week is about a fifth of a typical goal rate and roughly the width of
# the fit's own uncertainty at the minimum sample `weekly_rate` will answer on.
# Tighter than this and the check reports the noise in the regression rather
# than a change in behaviour.
RATE_TOLERANCE_KG_PER_WEEK = 0.15

# The four statuses, spelled once. `note` is not a verdict withheld -- it is a
# check that has no goal to compare against, like "your burn is measured rather
# than estimated". Forcing those into on/off track would invent a judgement the
# user never asked for and the app has no basis to make.
ON_TRACK = "on_track"
OFF_TRACK = "off_track"
NOTE = "note"
UNKNOWN = "unknown"


class DayIntake(NamedTuple):
    """One logged day's totals, as the router reads them out of `meals`."""

    date: date_type
    calories: float
    protein: float


class TargetsFacts(NamedTuple):
    """What `compute_targets` already worked out, as plain values.

    Deliberately not `targets.TargetsResult`: that module imports SQLAlchemy,
    and this one is stdlib-only so every function in it is testable without a
    database. The router does the unpacking, which is one place rather than
    every caller.
    """

    missing: tuple[str, ...]
    tdee: float | None
    tdee_source: str
    logged_days: int
    weigh_ins: int
    span_days: int
    basis_reason: str | None
    clamped_reason: str | None


class ReviewCheck(NamedTuple):
    """One question, its answer, and the sample the answer rests on.

    `value` and `target` are the two numbers the sentence compares, kept
    alongside it so the UI can render them without re-parsing prose, and so a
    test can assert the arithmetic without asserting the copy.

    `sample_days` is what **this** check was computed over, which is not the
    same for every check and is the field that stops the weight rate quietly
    claiming to describe seven days. `unavailable_reason` is None exactly when
    `status` is not `unknown`.
    """

    key: str
    status: str
    value: float | None
    target: float | None
    unit: str
    sample_days: int
    detail: str
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class WeeklyReview:
    """Everything the review endpoint reports.

    Field-for-field identical to `schemas.WeeklyReview`, deliberately: FastAPI
    runs this through `dataclasses.asdict` before validating against the
    response model, so a field the schema declares and this omits serializes
    silently as the schema's default rather than failing. `calibration.py` and
    `targets.py` both carry the same warning, and `test_review.py` pins it.
    """

    window_start: date_type
    window_end: date_type
    logged_days: int
    checks: list[ReviewCheck] = field(default_factory=list)


def _day_label(day: date_type) -> str:
    """`27 Aug`. Bare rather than localised: these strings are assembled here so
    they can be tested, and this app has no server-side locale to honour."""
    return f"{day.day} {day:%b}"


def _kcal(value: float) -> str:
    return f"{round(value):,}"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def logging_check(days: Sequence[DayIntake], window_end: date_type) -> ReviewCheck:
    """How much of the week is actually in the sample.

    First, and never absent, because it is the check that qualifies every other
    one. It also never refuses: a week with nothing logged is a complete answer
    to this question, and the only one where the rest of the review has nothing
    to describe.
    """
    logged = len(days)
    if logged == 0:
        return ReviewCheck(
            key="logging",
            status=OFF_TRACK,
            value=0,
            target=REVIEW_WINDOW_DAYS,
            unit="days",
            sample_days=REVIEW_WINDOW_DAYS,
            detail=(
                f"You logged no meals in the {REVIEW_WINDOW_DAYS} days ending "
                f"{_day_label(window_end)}, so there is nothing to review yet."
            ),
        )

    detail = (
        f"You logged meals on {logged} of the {REVIEW_WINDOW_DAYS} days ending "
        f"{_day_label(window_end)}."
    )
    if logged < LOGGING_DENSE_DAYS:
        # Said once, here, rather than repeated as a caveat on every figure
        # below -- each of those already names its own denominator.
        detail += (
            f" Everything below is averaged over "
            f"{'that day' if logged == 1 else 'those days'}, so it describes "
            f"{'it' if logged == 1 else 'them'} rather than the whole week."
        )
    return ReviewCheck(
        key="logging",
        status=ON_TRACK if logged >= LOGGING_DENSE_DAYS else OFF_TRACK,
        value=logged,
        target=REVIEW_WINDOW_DAYS,
        unit="days",
        sample_days=REVIEW_WINDOW_DAYS,
        detail=detail,
    )


def intake_check(
    days: Sequence[DayIntake], daily_target: float, plan_touched: bool
) -> ReviewCheck:
    """Mean calories per logged day against the target actually in force.

    `daily_target` is the *effective* target, not `settings.calorie_goal`: a
    calorie plan moves individual days, and `routers/plan.py` is emphatic that
    the stored goal and the effective one differ on exactly the days a plan
    touches. Reporting someone as 400 kcal over on a day they deliberately
    planned for would be the feature's first wrong answer.
    """
    if not days:
        return ReviewCheck(
            key="intake",
            status=UNKNOWN,
            value=None,
            target=round(daily_target, 1) if daily_target > 0 else None,
            unit="kcal",
            sample_days=0,
            detail="",
            unavailable_reason=(
                "No meals logged this week, so there is no average to compare "
                "against your target."
            ),
        )

    mean = sum(day.calories for day in days) / len(days)
    if daily_target <= 0:
        # Unreachable through the API -- schemas.Settings requires a positive
        # goal -- but a target of zero would make the tolerance band zero wide
        # and every week read as a miss, so it refuses rather than divides.
        return ReviewCheck(
            key="intake",
            status=UNKNOWN,
            value=round(mean, 1),
            target=None,
            unit="kcal",
            sample_days=len(days),
            detail="",
            unavailable_reason="You have no calorie target set to compare against.",
        )

    difference = mean - daily_target
    within = abs(difference) <= daily_target * INTAKE_TOLERANCE_FRACTION
    detail = (
        f"You averaged {_kcal(mean)} kcal on the {_plural(len(days), 'day')} you "
        f"logged, against a target of {_kcal(daily_target)}."
    )
    if not within:
        direction = "over" if difference > 0 else "under"
        detail += f" That is about {_kcal(abs(difference))} kcal a day {direction}."
    if plan_touched:
        # Named rather than folded in silently: a target that moved for a reason
        # the user chose should say so, or the comparison looks wrong to them.
        detail += " That target includes a calorie plan you set for these days."
    return ReviewCheck(
        key="intake",
        status=ON_TRACK if within else OFF_TRACK,
        value=round(mean, 1),
        target=round(daily_target, 1),
        unit="kcal",
        sample_days=len(days),
        detail=detail,
    )


def protein_check(days: Sequence[DayIntake], goal: float) -> ReviewCheck:
    """Mean protein, and how many days actually reached the goal.

    Both numbers, because they answer different questions and can disagree: a
    mean at the goal built from three days far over and three far under is not
    the same week as six days exactly on it, and only the day count separates
    them.
    """
    if not days:
        return ReviewCheck(
            key="protein",
            status=UNKNOWN,
            value=None,
            target=round(goal, 1),
            unit="g",
            sample_days=0,
            detail="",
            unavailable_reason=(
                "No meals logged this week, so protein cannot be summarised."
            ),
        )

    mean = sum(day.protein for day in days) / len(days)
    hits = sum(1 for day in days if day.protein >= goal)
    detail = (
        f"You averaged {round(mean)} g of protein against a {round(goal)} g goal, "
        f"reaching it on {hits} of the {_plural(len(days), 'day')} you logged."
    )
    return ReviewCheck(
        key="protein",
        status=ON_TRACK if hits >= len(days) * PROTEIN_HIT_FRACTION else OFF_TRACK,
        value=round(mean, 1),
        target=round(goal, 1),
        unit="g",
        sample_days=len(days),
        detail=detail,
    )


def _rate_phrase(rate: float) -> str:
    """How a measured weekly rate reads in a sentence.

    Under 0.05 kg/week is called steady rather than given a direction: the fit's
    own uncertainty is wider than that, so naming a direction there would be
    reporting the regression's noise as a finding about the person.
    """
    if abs(rate) < 0.05:
        return "holding steady"
    return f"{'falling' if rate < 0 else 'rising'} {abs(rate):.2f} kg a week"


def _goal_phrase(goal_rate: float) -> str:
    if goal_rate == 0:
        return "hold steady"
    return f"{'lose' if goal_rate < 0 else 'gain'} {abs(goal_rate):.2f} kg a week"


def weight_check(
    rate_kg: float | None,
    goal_rate_kg: float | None,
    weigh_ins: int,
    window_days: int,
    min_points: int,
    days_since_weigh_in: int | None = None,
) -> ReviewCheck:
    """Measured rate of change against the rate the user asked for.

    **This check is not about the last seven days and its sentence says so.**
    It reuses `weekly_rate`'s own window, because a seven-day weight slope is
    the exact noise `TDEE_MIN_SPAN_DAYS` exists to refuse -- `calculations.py`
    records a 7-day window producing 2700 kcal against 2498 from the formula
    off a 0.01 kg move. Publishing weekly does not license computing weekly.

    ⚠️ It also refuses a rate that is no longer current. `weekly_rate` windows
    from the **latest weigh-in**, not from today, so an account that stopped
    weighing in three months ago still gets a perfectly well-fitted slope --
    and rendering it here as "your trend weight is falling" would be a
    present-tense claim about a measurement that stopped. On the Weight page a
    chart of the actual dates saves it; a review has no such context, so the
    staleness has to be checked rather than shown.
    """
    if goal_rate_kg is None:
        return ReviewCheck(
            key="weight",
            status=UNKNOWN,
            value=rate_kg,
            target=None,
            unit="kg/week",
            sample_days=window_days,
            detail="",
            unavailable_reason=(
                "You have not set a goal rate, so there is nothing to compare "
                "your weight trend against."
            ),
        )
    if rate_kg is None:
        short = min_points - weigh_ins
        reason = (
            f"You have {_plural(weigh_ins, 'weigh-in')} in the last {window_days} "
            f"days. Weigh in on {short} more and your actual rate can be measured."
            if short > 0
            else (
                f"Your {_plural(weigh_ins, 'weigh-in')} do not yet spread across "
                f"enough days to fit a trend through."
            )
        )
        return ReviewCheck(
            key="weight",
            status=UNKNOWN,
            value=None,
            target=goal_rate_kg,
            unit="kg/week",
            sample_days=window_days,
            detail="",
            unavailable_reason=reason,
        )

    if days_since_weigh_in is not None and days_since_weigh_in > REVIEW_WINDOW_DAYS:
        return ReviewCheck(
            key="weight",
            status=UNKNOWN,
            value=rate_kg,
            target=goal_rate_kg,
            unit="kg/week",
            sample_days=window_days,
            detail="",
            unavailable_reason=(
                f"Your last weigh-in was {days_since_weigh_in} days ago, so "
                f"there is no current trend to compare. Weigh in and this "
                f"fills in again."
            ),
        )

    return ReviewCheck(
        key="weight",
        status=(
            ON_TRACK
            if abs(rate_kg - goal_rate_kg) <= RATE_TOLERANCE_KG_PER_WEEK
            else OFF_TRACK
        ),
        value=rate_kg,
        target=goal_rate_kg,
        unit="kg/week",
        sample_days=window_days,
        detail=(
            f"Your trend weight is {_rate_phrase(rate_kg)}; you asked to "
            f"{_goal_phrase(goal_rate_kg)}. Fitted over "
            f"{_plural(weigh_ins, 'weigh-in')} across the last {window_days} days, "
            f"not just this week — a seven-day slope is mostly day-to-day noise."
        ),
    )


def targets_check(facts: TargetsFacts) -> ReviewCheck:
    """Where the daily burn came from, and whether a target had to be capped.

    Pure pass-through: every string and number here was already computed by
    `targets.compute_targets`, and the only thing this feature adds is that
    somebody finally sees it outside the Settings card. `status` is `note`
    because there is no goal to be on or off track against -- a measured burn
    is not an achievement and an estimated one is not a failure.
    """
    if facts.missing:
        return ReviewCheck(
            key="targets",
            status=UNKNOWN,
            value=None,
            target=None,
            unit="kcal",
            sample_days=0,
            detail="",
            # Deliberately does not name the absent fields. The Settings card
            # already names each one precisely, and a second copy of that list
            # is a second thing to fall out of step with the profile.
            unavailable_reason=(
                "Your body profile is incomplete, so your daily burn cannot be "
                "worked out yet. Settings → Body says which part is missing."
            ),
        )

    if facts.tdee_source == "measured":
        detail = (
            f"Your daily burn is measured from your own logs: "
            f"{_kcal(facts.tdee or 0)} kcal, from {facts.logged_days} logged days "
            f"and {_plural(facts.weigh_ins, 'weigh-in')} over {facts.span_days} days."
        )
    else:
        detail = (
            f"Your daily burn is still estimated from a formula rather than "
            f"measured from your logs — {_kcal(facts.tdee or 0)} kcal."
        )
        if facts.basis_reason:
            detail += f" {facts.basis_reason}"
    if facts.clamped_reason:
        # ⚠️ Introduced, never appended bare. `target_calories`'s clamp sentence
        # has no subject of its own -- "Raised to 1521 kcal — the floor for your
        # estimated expenditure" -- so following a sentence about the daily
        # BURN it reads as though the burn was raised, when it is the calorie
        # target that moved. `clamp_measured_tdee`'s sentence does name its own
        # subject ("kcal a day burned"), and TargetsResult joins the two with a
        # space, so this lead-in has to be true whichever fired and cannot claim
        # which. Found in a real model summary repeating the ambiguity back.
        detail += f" Capped for safety: {facts.clamped_reason}"

    return ReviewCheck(
        key="targets",
        status=NOTE,
        value=facts.tdee,
        target=None,
        unit="kcal",
        sample_days=facts.span_days,
        detail=detail,
    )


def tracker_check(key: str, days_at_goal: int, goal_label: str) -> ReviewCheck:
    """Days a daily tracker reached its goal. Shared by water and steps.

    The denominator is the whole window, not the days the tracker was touched:
    a day you did not drink to your goal is a day you did not hit it, whether
    or not you opened the app. That is the opposite of the meal averages, and
    the difference is real -- an unlogged meal day means "did not log", where
    an unlogged water day means the goal was not reached.
    """
    return ReviewCheck(
        key=key,
        status=(
            ON_TRACK
            if days_at_goal >= REVIEW_WINDOW_DAYS * TRACKER_HIT_FRACTION
            else OFF_TRACK
        ),
        value=days_at_goal,
        target=REVIEW_WINDOW_DAYS,
        unit="days",
        sample_days=REVIEW_WINDOW_DAYS,
        detail=(
            f"You hit your {goal_label} on {days_at_goal} of the "
            f"{REVIEW_WINDOW_DAYS} days."
        ),
    )


def calibration_check(summary: CalibrationSummary | None) -> ReviewCheck | None:
    """How far the user moved the AI's calorie figures, if that is answerable.

    None -- absent from the review entirely -- when no meal has ever been saved
    from an estimate. There is a difference between "the app has nothing to say
    about its own accuracy yet" and "you have not used the AI", and only the
    second one deserves silence rather than a refusal sentence.

    Everything here comes from `calibration.summarise` unchanged. The full
    section stays on Analytics; this is the one line of it, which is what the
    roadmap ordered this phase after Phase 12 to be able to say.
    """
    if summary is None or summary.linked == 0:
        return None

    macro = summary.calories
    if macro.median_signed_error_pct is None:
        return ReviewCheck(
            key="calibration",
            status=UNKNOWN,
            value=None,
            target=None,
            unit="%",
            sample_days=0,
            detail="",
            unavailable_reason=macro.unavailable_reason,
        )

    moved = macro.median_signed_error_pct
    return ReviewCheck(
        key="calibration",
        status=NOTE,
        value=round(moved, 1),
        target=None,
        unit="%",
        sample_days=0,
        detail=(
            f"On the {_plural(macro.corrected, 'estimate')} you corrected, you "
            f"typically moved the calorie figure "
            f"{'up' if moved >= 0 else 'down'} {round(abs(moved))}%. Saving an "
            f"estimate unchanged measures nothing, so only corrections count here."
        ),
    )


def summarise(
    *,
    window_start: date_type,
    window_end: date_type,
    days: Sequence[DayIntake],
    daily_calorie_target: float,
    protein_goal: float,
    plan_touched: bool,
    targets: TargetsFacts,
    rate_kg: float | None,
    goal_rate_kg: float | None,
    weigh_ins: int,
    days_since_weigh_in: int | None = None,
    water_days_at_goal: int | None = None,
    steps_days_at_goal: int | None = None,
    steps_goal: int | None = None,
    calibration: CalibrationSummary | None = None,
    rate_window_days: int = RATE_WINDOW_DAYS,
    rate_min_points: int = RATE_MIN_POINTS,
) -> WeeklyReview:
    """Assemble the review. The router does the queries; this decides what is said.

    **A check the user has not opted into is absent, not empty.** The opt-in is
    read from answers they already gave rather than from a new setting:
    `steps_goal` is NULL until someone sets one and `models.py` says in as many
    words that NULL there means "I have no goal"; water has no such flag --
    NULL `water_goal_ml` means "derive it from my weight" -- so its signal is
    whether any water has ever been logged, which the router passes as None.

    ⚠️ Neither signal may be "did you use this *in the window*". "Logged nothing
    this week" and "does not use this tracker" are indistinguishable from the
    data, so a window-scoped test would hide the steps section from someone who
    does track steps and had a bad week -- exactly the week worth reading.
    """
    checks: list[ReviewCheck] = [
        logging_check(days, window_end),
        intake_check(days, daily_calorie_target, plan_touched),
        protein_check(days, protein_goal),
        weight_check(
            rate_kg,
            goal_rate_kg,
            weigh_ins,
            rate_window_days,
            rate_min_points,
            days_since_weigh_in,
        ),
        targets_check(targets),
    ]
    if water_days_at_goal is not None:
        checks.append(tracker_check("water", water_days_at_goal, "water goal"))
    if steps_goal is not None and steps_days_at_goal is not None:
        checks.append(
            tracker_check("steps", steps_days_at_goal, f"{steps_goal:,}-step goal")
        )
    calibration_line = calibration_check(calibration)
    if calibration_line is not None:
        checks.append(calibration_line)

    return WeeklyReview(
        window_start=window_start,
        window_end=window_end,
        logged_days=len(days),
        checks=checks,
    )
