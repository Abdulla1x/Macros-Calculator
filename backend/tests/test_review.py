"""The weekly review's arithmetic, and the refusals it makes instead of guessing."""
from datetime import date

import pytest

from app.calculations import RATE_MIN_POINTS, RATE_WINDOW_DAYS
from app.calibration import CalibrationSummary, MacroCalibration
from app.review import (
    INTAKE_TOLERANCE_FRACTION,
    LOGGING_DENSE_DAYS,
    NOTE,
    OFF_TRACK,
    ON_TRACK,
    REVIEW_WINDOW_DAYS,
    UNKNOWN,
    DayIntake,
    TargetsFacts,
    calibration_check,
    intake_check,
    logging_check,
    protein_check,
    summarise,
    targets_check,
    tracker_check,
    weight_check,
)

WINDOW_END = date(2026, 8, 27)
WINDOW_START = date(2026, 8, 21)

COMPLETE_PROFILE = TargetsFacts(
    missing=(),
    tdee=2540.0,
    tdee_source="measured",
    logged_days=14,
    weigh_ins=12,
    span_days=21,
    basis_reason=None,
    clamped_reason=None,
)


def days(count: int, calories: float = 2000.0, protein: float = 150.0):
    """`count` logged days, all identical, so a test perturbs one thing at a time."""
    return [DayIntake(date(2026, 8, 21 + n), calories, protein) for n in range(count)]


def review(**overrides):
    """`summarise` with a complete, on-track account, minus whatever is overridden."""
    kwargs = dict(
        window_start=WINDOW_START,
        window_end=WINDOW_END,
        days=days(6),
        daily_calorie_target=2000.0,
        protein_goal=150.0,
        plan_touched=False,
        targets=COMPLETE_PROFILE,
        rate_kg=-0.5,
        goal_rate_kg=-0.5,
        weigh_ins=12,
    )
    kwargs.update(overrides)
    return summarise(**kwargs)


def keys(result) -> list[str]:
    return [check.key for check in result.checks]


def by_key(result, key):
    return next(check for check in result.checks if check.key == key)


# --- the rule the whole feature turns on ---------------------------------------


def test_the_weight_check_describes_its_own_window_and_not_the_week():
    """The one claim this module must never make.

    Publishing weekly does not license computing weekly. A seven-day weight
    slope is the exact noise TDEE_MIN_SPAN_DAYS was chosen against, so the rate
    is fitted over `weekly_rate`'s own 28-day window -- and a sentence that let
    the reader believe otherwise would be the false precision this app exists
    to avoid. Pinned on both the number and the prose, because either alone
    could drift without the other.
    """
    check = weight_check(-0.4, -0.5, 12, RATE_WINDOW_DAYS, RATE_MIN_POINTS)

    assert check.sample_days == RATE_WINDOW_DAYS
    assert check.sample_days != REVIEW_WINDOW_DAYS
    assert f"last {RATE_WINDOW_DAYS} days" in check.detail
    assert "not just this week" in check.detail


def test_every_check_reports_the_window_it_actually_used():
    """Structural version of the same rule, across the whole review.

    The intake and weight checks disagreeing about `sample_days` is the point:
    a single window on the response would force one of them to lie.
    """
    result = review()

    assert by_key(result, "intake").sample_days == 6
    assert by_key(result, "protein").sample_days == 6
    assert by_key(result, "logging").sample_days == REVIEW_WINDOW_DAYS
    assert by_key(result, "weight").sample_days == RATE_WINDOW_DAYS


# --- which checks appear at all ------------------------------------------------


def test_a_tracker_with_no_goal_is_absent_rather_than_empty():
    """The opt-in, read from an answer the user already gave.

    `models.py` says a NULL `steps_goal` means "I have no goal", so someone who
    has never set one is not asked about steps at all. Absent, not a row of
    dashes -- an empty section is still the app bringing up a subject the user
    declined.
    """
    assert "steps" not in keys(review())
    assert "steps" in keys(review(steps_goal=10_000, steps_days_at_goal=3))


def test_water_opts_in_on_having_been_logged_not_on_a_goal():
    """Water's NULL means something different and cannot be reused as a flag.

    `water_goal_ml` NULL means "derive it from my weight", not "off", so unlike
    steps there is no column that carries the opt-in. The router passes None
    when the account has never logged water at all.
    """
    assert "water" not in keys(review())
    assert "water" in keys(review(water_days_at_goal=0))


def test_calibration_is_absent_until_a_meal_is_saved_from_an_estimate():
    """Silence and refusal are different answers.

    "The app cannot measure its own accuracy yet" is worth saying; "you have
    never used the AI" is not, and printing the first at someone who means the
    second is a refusal to a question they never asked.
    """
    assert calibration_check(None) is None
    assert calibration_check(summary(linked=0)) is None
    assert calibration_check(summary(linked=4)) is not None


def test_the_five_core_checks_are_always_present_even_on_an_empty_account():
    """A refusal that names what is missing beats an absent section here.

    These five are the review. "Weigh in on 3 more days and this can be
    measured" is the useful half of not having an answer -- the same contract
    TdeeBasis and calibration already keep.
    """
    result = review(
        days=[],
        rate_kg=None,
        goal_rate_kg=None,
        weigh_ins=0,
        targets=TargetsFacts((), None, "estimated", 0, 0, 0, None, None)._replace(
            missing=("height_cm",)
        ),
    )

    assert keys(result) == ["logging", "intake", "protein", "weight", "targets"]
    for key in ("intake", "protein", "weight", "targets"):
        check = by_key(result, key)
        assert check.status == UNKNOWN
        assert check.unavailable_reason


# --- logging -------------------------------------------------------------------


def test_logging_warns_that_the_averages_describe_the_days_not_the_week():
    """Said once, where the sample is, rather than as a caveat on every figure."""
    sparse = logging_check(days(LOGGING_DENSE_DAYS - 1), WINDOW_END)
    dense = logging_check(days(LOGGING_DENSE_DAYS), WINDOW_END)

    assert sparse.status == OFF_TRACK
    assert "rather than the whole week" in sparse.detail
    assert dense.status == ON_TRACK
    assert "rather than the whole week" not in dense.detail


def test_a_week_with_nothing_logged_answers_rather_than_refuses():
    """Logging is the sample, so it is the one check that cannot lack one."""
    check = logging_check([], WINDOW_END)

    assert check.status == OFF_TRACK
    assert check.unavailable_reason is None
    assert check.value == 0


def test_one_logged_day_is_not_described_in_the_plural():
    check = logging_check(days(1), WINDOW_END)

    assert "that day" in check.detail
    assert "those days" not in check.detail


# --- intake --------------------------------------------------------------------


@pytest.mark.parametrize(
    "mean, expected",
    [
        (2000 + 2000 * INTAKE_TOLERANCE_FRACTION, ON_TRACK),
        (2000 - 2000 * INTAKE_TOLERANCE_FRACTION, ON_TRACK),
        (2000 + 2000 * INTAKE_TOLERANCE_FRACTION + 1, OFF_TRACK),
        (2000 - 2000 * INTAKE_TOLERANCE_FRACTION - 1, OFF_TRACK),
    ],
)
def test_the_intake_band_is_inclusive_at_both_edges(mean, expected):
    """Exactly on the tolerance is inside it, the way `covered` is inclusive."""
    assert intake_check(days(6, calories=mean), 2000.0, False).status == expected


def test_intake_names_a_calorie_plan_that_moved_the_target():
    """A target that moved for a reason the user chose has to say so.

    `routers/plan.py` is emphatic that the stored goal and the effective one
    differ on exactly the days a plan touches. Comparing against the effective
    one and not mentioning it makes the app look wrong to the person who
    planned it.
    """
    assert "calorie plan" in intake_check(days(6), 2400.0, True).detail
    assert "calorie plan" not in intake_check(days(6), 2400.0, False).detail


def test_intake_refuses_rather_than_dividing_by_a_target_of_zero():
    """Unreachable through the API, and a zero-wide band would miss every week."""
    check = intake_check(days(6), 0.0, False)

    assert check.status == UNKNOWN
    assert check.value == 2000.0


# --- protein -------------------------------------------------------------------


def test_protein_reports_the_mean_and_the_day_count_because_they_disagree():
    """A mean on the goal built from extremes is not a week on the goal.

    Three days far over and three far under average out exactly; only the day
    count separates that from six days actually on target.
    """
    swinging = [
        DayIntake(date(2026, 8, 21 + n), 2000.0, 250.0 if n % 2 else 50.0)
        for n in range(6)
    ]
    check = protein_check(swinging, 150.0)

    assert check.value == 150.0
    assert check.status == OFF_TRACK
    assert "reaching it on 3 of the 6 days" in check.detail


def test_protein_counts_a_day_exactly_on_the_goal_as_reaching_it():
    assert protein_check(days(6, protein=150.0), 150.0).status == ON_TRACK


# --- weight --------------------------------------------------------------------


def test_weight_refuses_differently_for_no_goal_and_for_too_few_weigh_ins():
    """Two different things are missing and only one of them is the user's data."""
    no_goal = weight_check(-0.4, None, 12, RATE_WINDOW_DAYS, RATE_MIN_POINTS)
    no_rate = weight_check(None, -0.5, 4, RATE_WINDOW_DAYS, RATE_MIN_POINTS)

    assert "goal rate" in no_goal.unavailable_reason
    assert f"{RATE_MIN_POINTS - 4} more" in no_rate.unavailable_reason


def test_weight_does_not_invent_a_direction_inside_the_fits_own_noise():
    """Under 0.05 kg/week is called steady rather than given a direction.

    The regression's uncertainty at the minimum sample it will answer on is
    wider than that, so naming a direction there reports noise as a finding.
    """
    assert "holding steady" in weight_check(
        0.01, 0.0, 12, RATE_WINDOW_DAYS, RATE_MIN_POINTS
    ).detail


# --- targets -------------------------------------------------------------------


def test_targets_is_a_note_because_there_is_no_goal_to_miss():
    """A measured burn is not an achievement and an estimated one is not a failure."""
    assert targets_check(COMPLETE_PROFILE).status == NOTE


def test_targets_passes_the_clamp_explanation_through_verbatim():
    """The sentence was written in calculations.py, where the policy lives.

    Rewording it here would be a second copy of a safety explanation, and the
    two would drift.
    """
    reason = "Rate limited to 1 kg/week (you asked for -5)."
    check = targets_check(COMPLETE_PROFILE._replace(clamped_reason=reason))

    assert reason in check.detail


def test_an_estimated_burn_carries_the_reason_it_is_not_measured():
    basis = "Weigh in on 6 more days and your calorie burn can be measured."
    check = targets_check(
        COMPLETE_PROFILE._replace(tdee_source="estimated", basis_reason=basis)
    )

    assert basis in check.detail
    assert "still estimated" in check.detail


def test_targets_does_not_restate_the_missing_profile_fields():
    """The Settings card already names each one; a second list would drift."""
    check = targets_check(COMPLETE_PROFILE._replace(missing=("height_cm", "sex")))

    assert check.status == UNKNOWN
    assert "height" not in check.unavailable_reason
    assert "Settings" in check.unavailable_reason


# --- trackers ------------------------------------------------------------------


def test_a_tracker_measures_against_the_whole_week_not_the_days_it_was_touched():
    """The opposite denominator from the meal averages, deliberately.

    An unlogged meal day means "did not log"; a day you did not reach your
    water goal is a day you did not reach it, app open or not.
    """
    check = tracker_check("water", 3, "water goal")

    assert check.target == REVIEW_WINDOW_DAYS
    assert check.sample_days == REVIEW_WINDOW_DAYS


# --- calibration ---------------------------------------------------------------


def summary(linked: int, moved: float | None = 8.0) -> CalibrationSummary:
    macro = MacroCalibration(
        corrected=12,
        covered=9,
        coverage_pct=75.0 if moved is not None else None,
        coverage_low_pct=None,
        coverage_high_pct=None,
        median_abs_error_pct=moved,
        median_signed_error_pct=moved,
        unavailable_reason=None if moved is not None else "Not enough corrections yet.",
    )
    return CalibrationSummary(
        analyses=20,
        linked=linked,
        unreadable=0,
        accepted_unchanged=8,
        corrected=12,
        calories=macro,
        protein=macro,
    )


def test_calibration_refuses_with_calibrations_own_sentence():
    """One definition of that refusal, in the module that owns the statistics."""
    check = calibration_check(summary(linked=4, moved=None))

    assert check.status == UNKNOWN
    assert check.unavailable_reason == "Not enough corrections yet."


def test_calibration_says_which_direction_the_estimates_were_moved():
    up = calibration_check(summary(linked=12, moved=8.0))
    down = calibration_check(summary(linked=12, moved=-8.0))

    assert "up 8%" in up.detail
    assert "down 8%" in down.detail
    assert up.status == NOTE
