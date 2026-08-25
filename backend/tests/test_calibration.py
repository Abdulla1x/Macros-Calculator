"""Calibration arithmetic: what the AI estimated against what the user saved."""
import json

from app.calibration import (
    ACCEPTED_TOLERANCE_KCAL,
    CALIBRATION_MIN_SAMPLES,
    Bounds,
    Pair,
    ParsedEstimate,
    covered,
    parse_estimate,
    signed_error_pct,
    summarise,
    wilson_interval,
)

# A range wide enough that a correction can land inside or outside it on
# purpose, so no test depends on an accidental boundary.
CALORIES = Bounds(low=500.0, estimate=600.0, high=700.0)
PROTEIN = Bounds(low=20.0, estimate=25.0, high=30.0)


def estimate(confidence: str = "high") -> ParsedEstimate:
    return ParsedEstimate(calories=CALORIES, protein=PROTEIN, confidence=confidence)


def pairs(saved_calories: list[float], confidence: str = "high") -> list[Pair]:
    """Pairs that differ only in the calories the user saved.

    Protein is always saved at its estimate, so a test about calories cannot be
    perturbed by protein crossing the accepted/corrected line behind its back.
    """
    return [Pair(estimate(confidence), value, PROTEIN.estimate) for value in saved_calories]


def test_the_summary_dataclass_and_its_response_schema_stay_identical():
    """The asdict trap, pinned.

    FastAPI runs the dataclass through `dataclasses.asdict` before validating it
    against the response model, so a field the schema declares and the dataclass
    omits does not fail -- it serializes as the schema's default, silently. A
    drift here would ship a number that is always the same wrong value.
    """
    import dataclasses

    from app.calibration import CalibrationSummary
    from app.schemas import Calibration

    assert {f.name for f in dataclasses.fields(CalibrationSummary)} == set(
        Calibration.model_fields
    )


# --- parsing -----------------------------------------------------------------


def test_parse_estimate_reads_a_stored_payload():
    raw = json.dumps(
        {
            "calories": {"low": 500, "estimate": 600, "high": 700},
            "protein": {"low": 20, "estimate": 25, "high": 30},
            "confidence": "medium",
        }
    )
    parsed = parse_estimate(raw)

    assert parsed is not None
    assert parsed.calories == CALORIES
    assert parsed.confidence == "medium"


def test_parse_estimate_treats_an_empty_payload_as_normal_not_as_damage(caplog):
    """A reserved-but-unfilled row is routine, and json.loads("") raises.

    Returning None is not enough to prove the guard is doing its job -- the
    except clause below it would return None too, while logging every
    transcription row in the table as unreadable. The guard exists so that a
    normal row stays silent, so silence is what this asserts.

    routers/data.py carries the scar from the other half of this: the same empty
    string 500'd the whole export for anyone who had recorded a voice note.
    """
    assert parse_estimate("") is None
    assert parse_estimate(None) is None
    assert caplog.text == ""


def test_parse_estimate_warns_rather_than_raising_on_unreadable_json(caplog):
    assert parse_estimate("{not json at all") is None
    assert "not readable JSON" in caplog.text


def test_parse_estimate_tolerates_a_null_bound_that_was_legal_when_written():
    """A non-finite float serializes to null, and the schema would reject it.

    schemas.py carries no numeric constraints on the analysis models because
    Gemini rejects them, so this row was valid on the way in. Re-validating
    through MealAnalysis would raise; this module must not.
    """
    raw = json.dumps(
        {
            "calories": {"low": None, "estimate": 600, "high": 700},
            "protein": {"low": 20, "estimate": 25, "high": 30},
            "confidence": "high",
        }
    )
    parsed = parse_estimate(raw)

    assert parsed is not None
    assert parsed.calories is None  # unusable
    assert parsed.protein == PROTEIN  # but protein still counts


def test_parse_estimate_returns_none_when_no_macro_survives():
    raw = json.dumps({"calories": {"low": None}, "protein": None, "confidence": "high"})
    assert parse_estimate(raw) is None


def test_parse_estimate_orders_a_backwards_range_rather_than_dropping_it():
    """low > high is a provider bug, not a fact about the user's meal."""
    raw = json.dumps({"calories": {"low": 700, "estimate": 600, "high": 500}, "protein": None})
    parsed = parse_estimate(raw)

    assert parsed is not None
    assert parsed.calories == Bounds(500.0, 600.0, 700.0)


# --- the primitives ----------------------------------------------------------


def test_covered_includes_both_boundaries():
    """A value exactly on the bound was inside the claim the app made."""
    assert covered(CALORIES, 500.0)
    assert covered(CALORIES, 700.0)
    assert not covered(CALORIES, 499.9)
    assert not covered(CALORIES, 700.1)


def test_signed_error_is_positive_when_the_user_revised_upward():
    assert signed_error_pct(600.0, 660.0) == 10.0
    assert signed_error_pct(600.0, 540.0) == -10.0


def test_signed_error_is_none_for_a_zero_estimate_rather_than_infinite():
    """A percentage of nothing is undefined, not enormous.

    Returning a huge number instead would let one degenerate row dominate every
    median computed downstream.
    """
    assert signed_error_pct(0.0, 100.0) is None


def test_wilson_interval_stays_inside_zero_and_one_hundred_without_clamping():
    """The reason it is Wilson and not the normal approximation.

    At a proportion of 1.0 the textbook interval is 100% +/- 0, and at 0.9 with
    n=10 its upper bound runs past 100% -- a coverage rate of "119%" printed by
    a feature about honest numbers would discredit it. The score interval cannot
    do that however extreme the proportion, which is why nothing here clamps.
    """
    for hits, total in ((10, 10), (0, 10), (9, 10), (1, 12)):
        low, high = wilson_interval(hits, total)
        assert 0.0 <= low <= high <= 100.0, (hits, total, low, high)

    # The alternative this rejects, at the same inputs.
    naive_high = 0.9 + 1.96 * (0.9 * 0.1 / 10) ** 0.5
    assert naive_high > 1.0


def test_wilson_interval_narrows_as_the_sample_grows():
    small = wilson_interval(8, 10)
    large = wilson_interval(80, 100)
    assert (small[1] - small[0]) > (large[1] - large[0])


def test_wilson_interval_is_none_for_an_empty_sample():
    assert wilson_interval(0, 0) is None


# --- the aggregate -----------------------------------------------------------


def test_an_accepted_estimate_is_not_counted_as_a_correction():
    """The trap this whole module is arranged around.

    Saving the estimate untouched makes the saved value *be* the estimate, so it
    is inside its own range by construction. Counting those would produce a
    coverage rate near 100% that measures nothing but its own definition.
    """
    summary = summarise(pairs([CALORIES.estimate] * 20), analyses=20, linked=20, unreadable=0)

    assert summary.accepted_unchanged == 20
    assert summary.corrected == 0
    assert summary.calories.corrected == 0
    assert summary.calories.coverage_pct is None


def test_a_meal_within_the_rounding_tolerance_still_counts_as_accepted():
    """The meal total is summed from item rows, so float addition can drift."""
    nudged = CALORIES.estimate + ACCEPTED_TOLERANCE_KCAL / 2
    summary = summarise(pairs([nudged]), analyses=1, linked=1, unreadable=0)

    assert summary.accepted_unchanged == 1


def test_a_meal_corrected_on_protein_alone_is_still_a_correction():
    """The user looked and changed something, even if calories stayed put."""
    pair = Pair(estimate(), CALORIES.estimate, PROTEIN.estimate + 5)
    summary = summarise([pair], analyses=1, linked=1, unreadable=0)

    assert summary.accepted_unchanged == 0
    assert summary.corrected == 1
    assert summary.calories.corrected == 0  # calories genuinely did not move
    assert summary.protein.corrected == 1


def test_coverage_is_measured_over_the_corrected_subset_only():
    """Nine accepted meals must not dilute the ten corrections into a rate."""
    accepted = [CALORIES.estimate] * 9
    inside = [650.0] * 8  # within 500-700
    outside = [900.0] * 2  # beyond it
    summary = summarise(
        pairs(accepted + inside + outside), analyses=21, linked=21, unreadable=0
    )

    assert summary.calories.corrected == 10
    assert summary.calories.covered == 8
    assert summary.calories.coverage_pct == 80.0


def test_the_minimum_sample_is_a_refusal_not_a_rounded_number():
    """Below / at / above the policy floor."""
    inside = [650.0]
    below = summarise(pairs(inside * (CALIBRATION_MIN_SAMPLES - 1)), 9, 9, 0)
    at = summarise(pairs(inside * CALIBRATION_MIN_SAMPLES), 10, 10, 0)

    assert below.calories.coverage_pct is None
    assert below.calories.unavailable_reason is not None
    assert at.calories.coverage_pct == 100.0
    assert at.calories.unavailable_reason is None


def test_a_refusal_still_reports_how_many_corrections_there_are():
    """A refusal that hides how close you are to an answer is just a shrug."""
    summary = summarise(pairs([650.0, 660.0, 670.0]), analyses=3, linked=3, unreadable=0)

    assert summary.calories.corrected == 3
    assert "3 of 3" in summary.calories.unavailable_reason
    assert "7 more" in summary.calories.unavailable_reason


def test_one_macro_can_answer_while_the_other_refuses():
    """Protein and calories fill up at different speeds, and really did.

    On the account this shipped against protein had eleven corrections and
    calories three. A single section-wide refusal would have printed a false
    statement directly above a real protein number.
    """
    rows = [Pair(estimate(), CALORIES.estimate, 27.0) for _ in range(CALIBRATION_MIN_SAMPLES)]
    summary = summarise(rows, analyses=10, linked=10, unreadable=0)

    assert summary.protein.coverage_pct == 100.0
    assert summary.protein.unavailable_reason is None
    assert summary.calories.coverage_pct is None
    assert summary.calories.unavailable_reason is not None
    # And the section-wide reason stays silent, because something was measurable.
    assert summary.unavailable_reason is None


def test_an_empty_log_is_not_described_as_a_choice_the_user_made():
    """Found in production, on a brand-new account.

    The refusal used to read "you have saved 0 meals ... and left almost all of
    them as they were", which asserts a decision nobody took. The UI happens to
    short-circuit before rendering it, which is exactly the "known, therefore
    harmless" shape this project has shipped three times already.
    """
    summary = summarise([], analyses=0, linked=0, unreadable=0)

    assert "0 meals" not in summary.unavailable_reason
    assert "left almost all" not in summary.unavailable_reason
    assert "0 of 0" not in summary.calories.unavailable_reason


def test_the_section_refuses_only_when_no_macro_can_speak():
    summary = summarise(pairs([CALORIES.estimate] * 5), analyses=5, linked=5, unreadable=0)

    assert summary.unavailable_reason is not None
    assert "Nothing to measure yet" in summary.unavailable_reason


def test_counts_of_the_whole_log_survive_a_refusal():
    """Reported straight from the table, so a refusal names the real total.

    targets.py makes the same choice: computing the counts after the guards
    would report `0` at someone who has logged for three weeks.
    """
    summary = summarise(pairs([CALORIES.estimate]), analyses=123, linked=67, unreadable=4)

    assert summary.analyses == 123
    assert summary.linked == 67
    assert summary.unreadable == 4


def test_confidence_buckets_split_the_corrected_pairs_by_badge():
    """The test of whether the badge means anything at all."""
    high = pairs([650.0] * CALIBRATION_MIN_SAMPLES, confidence="high")
    low = pairs([900.0] * 4, confidence="low")
    summary = summarise(high + low, analyses=14, linked=14, unreadable=0)

    buckets = {bucket.confidence: bucket for bucket in summary.by_confidence}
    assert buckets["high"].coverage_pct == 100.0
    assert buckets["low"].coverage_pct == 0.0


def test_confidence_buckets_are_empty_while_calories_cannot_answer():
    """The badge qualifies the headline calorie range, so it waits for it."""
    summary = summarise(pairs([650.0, 900.0]), analyses=2, linked=2, unreadable=0)

    assert summary.by_confidence == []


def test_a_zero_estimate_does_not_poison_the_median_error():
    rows = pairs([650.0] * CALIBRATION_MIN_SAMPLES)
    rows.append(Pair(ParsedEstimate(Bounds(0.0, 0.0, 0.0), None, "high"), 400.0, 0.0))
    summary = summarise(rows, analyses=11, linked=11, unreadable=0)

    assert summary.calories.median_abs_error_pct is not None
    assert summary.calories.median_abs_error_pct < 100
