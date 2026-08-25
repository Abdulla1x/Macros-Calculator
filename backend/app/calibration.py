"""Calibration: how the AI's estimates compare to what you actually saved.

The arithmetic only. No database, no request, no `now` of its own -- every
function takes what it needs, so all of it is testable without a fixture, the
way `calculations.py` is.

Every meal analysis is shown to the user as a point estimate inside a `low`-
`high` range, with a confidence badge. Those bounds come from the model, asked
for in `services/meal_ai.py`'s prompt; nothing has ever checked them. This
module is that check, and because it is a check about honesty, getting the
statistics wrong here would repeat the exact sin it exists to catch. Four traps,
all of them load-bearing:

  * **Coverage on an accepted estimate is true by construction.** If the user
    saves the estimate untouched, the saved value *is* the estimate, so it sits
    inside its own range necessarily. Accepting is by far the common path -- on
    the account this was built against, 61 of 64 linked meals were saved with
    the calorie figure unchanged to the decimal. A coverage rate computed over
    all of them would read ~100% and would be measuring nothing but its own
    definition. Coverage is therefore computed over the **corrected** subset
    only, and the accepted count is reported separately as its own number.

  * **A saved meal is not ground truth.** It is the user's own estimate, unless
    they weighed the food. So the honest phrasing of every error figure here is
    "how far you moved the AI's number", never "how wrong the AI was" -- and
    that belongs in the copy on screen, not only in this docstring.

  * **The sample is not a random sample of meals.** A pair exists only when the
    user tapped "Use these ingredients" *and* the follow-up link request landed;
    the client swallows that failure silently, and a deleted meal nulls the link
    afterwards. Every count here is a lower bound on what actually happened.

  * **A high acceptance rate is not evidence of accuracy.** It is equally
    consistent with trusting the number without checking it. Acceptance measures
    behaviour, not correctness, and the two must not be conflated on screen.

What this module refuses to do: report a rate it cannot support. Below
CALIBRATION_MIN_SAMPLES the counts are still returned -- they are the useful
part of a refusal -- but every derived rate is None and `unavailable_reason`
says, in a sentence, what is still missing. That mirrors `TdeeBasis`, for the
same reason: "you are seven corrections away from an answer" is far more useful
than a confident number built on three.
"""
import json
import logging
import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)

# POLICY. How many corrected estimates before a coverage rate is worth printing.
#
# Unlike the TDEE minimums in calculations.py, this one is NOT chosen against
# real data, because there is none yet -- the account this shipped against had
# exactly three corrections. It is a statistical floor rather than an empirical
# one: a proportion from n observations carries a 95% interval roughly +/-1/sqrt(n)
# wide, so even at n=10 an observed 80% still spans about 49-94%. Ten is where
# the interval stops being wider than the range of answers it is choosing
# between. Revisit it against real corrections rather than tuning it by feel.
CALIBRATION_MIN_SAMPLES = 10

# CONVENTION. How close a saved value has to be to count as "accepted
# unchanged". This is a float-rounding guard, not a judgement about intent: the
# meal total is summed from the item rows, so a value the user never touched can
# land a hair off the estimate through ordinary floating-point addition. A user
# who edits two items so they cancel out is counted as accepting, which is
# correct -- this measures the number, not the intention behind it.
ACCEPTED_TOLERANCE_KCAL = 0.5
ACCEPTED_TOLERANCE_G = 0.05

# CONVENTION. z for a 95% interval. Wilson rather than the textbook normal
# approximation because the normal one produces bounds outside [0, 1] at small n
# and at proportions near 0 or 1 -- which is precisely the regime this feature
# lives in, and printing a coverage rate of "104%" would be a fitting way to
# discredit a feature about honest numbers.
WILSON_Z = 1.96


class Bounds(NamedTuple):
    """One macro's estimate and the range it was shown inside."""

    low: float
    estimate: float
    high: float


class ParsedEstimate(NamedTuple):
    """The parts of a stored analysis this module can use.

    Deliberately not `schemas.MealAnalysis`: that model is handed to Gemini as a
    structured-output schema and so carries no numeric constraints, which means
    a non-finite float was serialized to `null` and re-validating the row would
    *raise* on data that was perfectly legal when written. Parsing by hand keeps
    this module stdlib-only and lets a half-readable row contribute the half
    that reads.
    """

    calories: Bounds | None
    protein: Bounds | None
    confidence: str | None


class Pair(NamedTuple):
    """One analysis matched to the meal the user actually saved from it."""

    estimate: ParsedEstimate
    saved_calories: float
    saved_protein: float


class MacroCalibration(NamedTuple):
    """One macro's answer, with the sample it rests on.

    The counts are populated whether or not the rates are. A refusal that also
    hides how close you are to an answer is just a shrug.
    """

    corrected: int
    covered: int
    coverage_pct: float | None
    coverage_low_pct: float | None
    coverage_high_pct: float | None
    median_abs_error_pct: float | None
    median_signed_error_pct: float | None
    unavailable_reason: str | None


class ConfidenceBucket(NamedTuple):
    """Coverage split by the badge the user was shown.

    This is the test of whether the badge means anything: if "high" and "medium"
    cover at the same rate, the badge is decoration. Note the prompt in
    services/meal_ai.py defines only "high" and "low", so "medium" is an
    unlabelled middle the model reaches for on its own.
    """

    confidence: str
    corrected: int
    covered: int
    coverage_pct: float | None


def _num(value: Any) -> float | None:
    """A finite float, or None. Tolerates the string forms JSON round-trips."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _bounds(raw: Any) -> Bounds | None:
    """One macro's range, or None if any of the three numbers is unusable."""
    if not isinstance(raw, dict):
        return None
    low, estimate, high = _num(raw.get("low")), _num(raw.get("estimate")), _num(raw.get("high"))
    if low is None or estimate is None or high is None:
        return None
    # A range stored the wrong way round is a provider bug, not a user fact.
    # Ordering it here rather than dropping the row keeps the estimate usable.
    return Bounds(min(low, high), estimate, max(low, high))


def parse_estimate(analysis_json: str | None) -> ParsedEstimate | None:
    """Read a stored analysis payload, tolerating one that cannot be read.

    Returns None only when there is nothing usable at all. An empty string is
    normal rather than exceptional -- a row is written when the provider call is
    reserved and filled in when it returns, and a call that produced unusable
    output deliberately keeps its row so the quota stays spent. `json.loads("")`
    raises, and data.py carries the scar from finding that out in production.

    Follows routers/meal_templates.py: warn and skip, because one unreadable row
    must not take a whole page's worth of numbers down with it.
    """
    if not analysis_json:
        return None
    try:
        payload = json.loads(analysis_json)
    except (ValueError, TypeError):
        logger.warning("ai_analysis payload is not readable JSON")
        return None
    if not isinstance(payload, dict):
        return None

    confidence = payload.get("confidence")
    parsed = ParsedEstimate(
        calories=_bounds(payload.get("calories")),
        protein=_bounds(payload.get("protein")),
        confidence=confidence if isinstance(confidence, str) else None,
    )
    # Nothing numeric survived, so the row cannot contribute to any figure.
    if parsed.calories is None and parsed.protein is None:
        return None
    return parsed


def covered(bounds: Bounds, saved: float) -> bool:
    """Did the value the user saved land inside the range they were shown?

    Inclusive at both ends: a value exactly on the boundary was inside the claim
    the app made, and excluding it would flatter the range's failures.
    """
    return bounds.low <= saved <= bounds.high


def signed_error_pct(estimate: float, saved: float) -> float | None:
    """How far the user moved the number, as a percentage of the estimate.

    Positive means they revised *upward*, i.e. the estimate had been low. None
    when the estimate is zero -- a percentage of nothing is not a large error,
    it is an undefined one, and returning a huge number instead would let a
    single degenerate row dominate a median.
    """
    if estimate == 0:
        return None
    return (saved - estimate) / estimate * 100.0


def wilson_interval(hits: int, total: int, z: float = WILSON_Z) -> tuple[float, float] | None:
    """A 95% interval for a proportion, as percentages. None if unanswerable.

    The score interval rather than the normal approximation, for the reason
    given at WILSON_Z. This is the feature stating its own thesis: a coverage
    rate is itself an estimate, and printing it without its uncertainty would be
    the same false precision the range calibration exists to expose.
    """
    if total <= 0 or hits < 0 or hits > total:
        return None
    proportion = hits / total
    denominator = 1 + z**2 / total
    centre = (proportion + z**2 / (2 * total)) / denominator
    spread = z * math.sqrt(proportion * (1 - proportion) / total + z**2 / (4 * total**2)) / denominator
    # The score interval cannot leave [0, 1] mathematically, however extreme the
    # proportion -- that is why it is the one used here. Floating point is less
    # careful: at zero hits the lower bound lands a few times 1e-15 under zero,
    # which would render as "-0%". The clamp is for that and nothing else.
    return max(0.0, centre - spread) * 100.0, min(1.0, centre + spread) * 100.0


def _median(values: Sequence[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


@dataclass(frozen=True)
class CalibrationSummary:
    """Everything the calibration endpoint reports, and the sample behind it.

    Field-for-field identical to `schemas.Calibration`, deliberately: FastAPI
    runs this through `dataclasses.asdict` before validating against the
    response model, so a field the schema declares and this omits serializes
    silently as the schema's default rather than failing. targets.py carries the
    same warning over TdeeBasis.

    `unavailable_reason` is None exactly when a coverage rate was produced.
    """

    analyses: int
    linked: int
    unreadable: int
    accepted_unchanged: int
    corrected: int
    calories: MacroCalibration
    protein: MacroCalibration
    by_confidence: list[ConfidenceBucket] = field(default_factory=list)
    unavailable_reason: str | None = None


def _macro(
    pairs: Sequence[tuple[Bounds, float]],
    tolerance: float,
    min_samples: int,
    noun: str,
    total: int,
) -> tuple[MacroCalibration, list[tuple[Bounds, float]]]:
    """One macro's figures, plus the corrected pairs behind them.

    Returns the corrected subset as well so the caller can bucket it by
    confidence without re-deriving which pairs counted.

    The refusal lives here rather than on the summary because the two macros
    fill up at different speeds and genuinely disagree: on the account this was
    built against, protein had eleven corrections and calories three. A single
    section-wide "not enough data" would have been a false statement printed
    directly above a real protein number.
    """
    corrected = [
        (bounds, saved) for bounds, saved in pairs if abs(saved - bounds.estimate) > tolerance
    ]
    hits = sum(1 for bounds, saved in corrected if covered(bounds, saved))

    if len(corrected) < min_samples:
        # The counts survive the refusal; only the rates are withheld.
        short = min_samples - len(corrected)
        if total == 0:
            reason = (
                f"No estimates saved yet. Once {min_samples} of them have had "
                f"their {noun} corrected, the app can measure how often that "
                f"range was right."
            )
        else:
            reason = (
                f"You have changed the {noun} on {len(corrected)} of {total} "
                f"estimates you saved. {short} more and the app can measure how "
                f"often that range was right — below that, the rate would move "
                f"further than the answer it is meant to give."
            )
        return (
            MacroCalibration(len(corrected), hits, None, None, None, None, None, reason),
            corrected,
        )

    errors = [
        error
        for bounds, saved in corrected
        if (error := signed_error_pct(bounds.estimate, saved)) is not None
    ]
    interval = wilson_interval(hits, len(corrected))
    return (
        MacroCalibration(
            corrected=len(corrected),
            covered=hits,
            coverage_pct=hits / len(corrected) * 100.0,
            coverage_low_pct=interval[0] if interval else None,
            coverage_high_pct=interval[1] if interval else None,
            median_abs_error_pct=_median([abs(error) for error in errors]),
            median_signed_error_pct=_median(errors),
            unavailable_reason=None,
        ),
        corrected,
    )


def summarise(
    pairs: Sequence[Pair],
    analyses: int,
    linked: int,
    unreadable: int,
    min_samples: int = CALIBRATION_MIN_SAMPLES,
) -> CalibrationSummary:
    """Turn matched analysis/meal pairs into the figures the UI shows.

    `analyses` and `linked` are counted by the caller straight from the table,
    before any parsing, so a refusal reports the true size of the log rather
    than the size of the subset that happened to parse. targets.py makes the
    same choice for the same reason.

    "Accepted unchanged" is judged across every macro both sides reported: a
    meal counts as accepted only if nothing moved. A meal whose calories were
    left alone but whose protein was corrected is a correction, because the user
    did look and did change something.
    """
    calorie_pairs = [(p.estimate.calories, p.saved_calories) for p in pairs if p.estimate.calories]
    protein_pairs = [(p.estimate.protein, p.saved_protein) for p in pairs if p.estimate.protein]

    accepted = 0
    for pair in pairs:
        moved = False
        if pair.estimate.calories:
            moved |= (
                abs(pair.saved_calories - pair.estimate.calories.estimate)
                > ACCEPTED_TOLERANCE_KCAL
            )
        if pair.estimate.protein:
            moved |= (
                abs(pair.saved_protein - pair.estimate.protein.estimate) > ACCEPTED_TOLERANCE_G
            )
        accepted += 0 if moved else 1

    calories, corrected_calories = _macro(
        calorie_pairs, ACCEPTED_TOLERANCE_KCAL, min_samples, "calories", len(pairs)
    )
    protein, _ = _macro(
        protein_pairs, ACCEPTED_TOLERANCE_G, min_samples, "protein", len(pairs)
    )

    buckets: list[ConfidenceBucket] = []
    if calories.coverage_pct is not None:
        by_badge: dict[str, list[tuple[Bounds, float]]] = {}
        for pair in pairs:
            if pair.estimate.calories is None or pair.estimate.confidence is None:
                continue
            bounds = pair.estimate.calories
            if abs(pair.saved_calories - bounds.estimate) <= ACCEPTED_TOLERANCE_KCAL:
                continue
            by_badge.setdefault(pair.estimate.confidence, []).append(
                (bounds, pair.saved_calories)
            )
        for badge in ("high", "medium", "low"):
            entries = by_badge.get(badge)
            if not entries:
                continue
            hits = sum(1 for bounds, saved in entries if covered(bounds, saved))
            buckets.append(
                ConfidenceBucket(badge, len(entries), hits, hits / len(entries) * 100.0)
            )

    # Section-wide, and only when neither macro can say anything -- otherwise the
    # per-macro sentences carry it and this would contradict one of them.
    #
    # The two cases are genuinely different and must not share a sentence. With
    # no pairs at all there is nothing to characterise; saying someone "left
    # them as they were" describes a choice they never made.
    reason = None
    if calories.coverage_pct is None and protein.coverage_pct is None:
        if not pairs:
            reason = (
                "Nothing to measure yet. Analyse a meal, use the ingredients it "
                "finds, and save it — once you correct an estimate before "
                "saving, the app has something to check itself against."
            )
        else:
            reason = (
                f"Nothing to measure yet. You have saved {len(pairs)} "
                f"{'meal' if len(pairs) == 1 else 'meals'} from an AI estimate "
                f"and changed almost nothing, so there is little to compare "
                f"against. Correcting an estimate before saving is what gives "
                f"the app something to check itself against."
            )

    return CalibrationSummary(
        analyses=analyses,
        linked=linked,
        unreadable=unreadable,
        accepted_unchanged=accepted,
        corrected=len(pairs) - accepted,
        calories=calories,
        protein=protein,
        by_confidence=buckets,
        unavailable_reason=reason,
    )
