"""Send the same meal photos through the real model in several variants, and
say whether the variants change the estimate by more than the model's own noise.

Built to choose the on-device photo size (full size vs 1536 vs 1024 px) and
kept for the next question of the same shape: whether a newer model estimates
differently from the current one. Either way it is an accuracy decision, and an
accuracy decision needs a number, not a hunch.

**Photo-only, on purpose.** The app's best estimates come from typed weights,
and with weights in the note both variants converge on the text and any
difference in what the model *sees* disappears. A photo with no words is the
input where the image has to carry the whole estimate, so it is where a
difference would show.

**Repeats are the point, not a nicety.** The model runs at temperature 0.2, so
the same photo twice gives two answers. A variant that moves the estimate by
40 kcal means nothing until it is set against how far the same variant moves
between two identical calls -- this reports that spread beside every delta.

It also records input, output and thinking tokens per call: output and thinking
are billed at the output price, so they are what a per-call cost is made of.

The request is the app's own: `meal_ai._build_contents` and
`meal_ai.analysis_config`, so the prompt, schema and temperature cannot drift
from production. Unlike the app there is no fallback model: a call answered by
a different model would look like an effect of the variant.

Layout -- one subfolder per variant, the same meal under the same stem in each
(extensions may differ, since a shrunk photo is always .jpg):

    photos/
      original/  lunch.HEIC  pasta.jpg ...
      1536/      lunch.jpg   pasta.jpg ...
      1024/      lunch.jpg   pasta.jpg ...

Usage, from backend/ with GEMINI_API_KEY in the environment:

    venv/bin/python scripts/compare_estimates.py --photos ~/ab/photos \\
        --out ~/ab/results.csv
    venv/bin/python scripts/compare_estimates.py --photos ~/ab/photos \\
        --variants original --models gemini-3.5-flash gemini-3.8-flash \\
        --out ~/ab/models.csv

⚠️ These calls go straight to Google, not through the app, so the app's quota
does not count them -- but Google's does. If this key is the production key,
the free tier's requests-per-day are shared with real users: use --pause, and
--resume to finish another day. Each row is written as soon as it arrives.

A refusal for the DAY stops the run at once (see DailyQuotaReached).

Keep photos and results OUTSIDE the repository. They are someone's meals.
"""
import argparse
import asyncio
import csv
import os
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from google.genai import types  # noqa: E402

from app.schemas import MealAnalysis  # noqa: E402
from app.services import meal_ai  # noqa: E402

MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
}
FIELDS = [
    "meal", "variant", "model", "repeat", "bytes", "prompt_tokens",
    "output_tokens", "thinking_tokens",
    "kcal_low", "kcal", "kcal_high", "protein", "confidence", "items",
    "seconds", "attempts", "error",
]
# Overload (503) and per-minute limits (429) are routine on the free tier.
# Waiting them out is what the app does too; a give-up here is recorded as an
# error row and skipped by the summary, never counted as an estimate.
MAX_ATTEMPTS = 4
RETRY_WAIT_S = 15
RATE_LIMIT_WAIT_S = 65


class DailyQuotaReached(Exception):
    """Google refused for the DAY, not the minute: stop, don't retry.

    Retrying a per-day refusal cannot succeed before midnight Pacific, and on a
    key shared with production every extra call is one more the app's users
    cannot make. Per-minute refusals carry a different quota id and are waited
    out like overload.
    """


def quota_ids(exc: Exception) -> list[str]:
    """The quota ids a 429 names, from the structured error, not its prose.

    Matching the message text is not enough: the first version of this guard
    searched it for "PerDay" and stopped a run on what was a per-minute
    refusal -- the model answered again seconds later.
    """
    details = getattr(exc, "details", None)
    error = details.get("error", details) if isinstance(details, dict) else {}
    return [
        violation.get("quotaId", "")
        for item in (error or {}).get("details", []) or []
        for violation in item.get("violations", []) or []
    ]


def is_daily_quota(exc: Exception) -> bool:
    return any("PerDay" in quota for quota in quota_ids(exc))


def photos_by_meal(variant_dir: Path) -> dict[str, Path]:
    return {
        path.stem: path
        for path in sorted(variant_dir.iterdir())
        if path.suffix.lower() in MIME
    }


async def estimate(model: str, photo: Path) -> dict:
    data = photo.read_bytes()
    contents = meal_ai._build_contents(
        [(data, MIME[photo.suffix.lower()])], None, None
    )
    config = meal_ai.analysis_config(
        types.HttpOptions(timeout=meal_ai.ANALYZE_TIMEOUT_MS)
    )
    row: dict = {"bytes": len(data)}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        started = time.monotonic()
        try:
            response = await meal_ai._generate(model, contents, config)
        except Exception as exc:  # recorded, then retried or given up on
            if is_daily_quota(exc):
                raise DailyQuotaReached(", ".join(quota_ids(exc))) from exc
            quotas = quota_ids(exc)
            row["error"] = (
                f"429 {','.join(quotas)}" if quotas
                else f"{type(exc).__name__}: {str(exc)[:120]}"
            )
            if attempt < MAX_ATTEMPTS:
                # A per-minute quota needs the whole minute to pass; overload
                # clears faster.
                await asyncio.sleep(RATE_LIMIT_WAIT_S if quotas else RETRY_WAIT_S)
            continue
        row["seconds"] = round(time.monotonic() - started, 1)
        row["attempts"] = attempt
        usage = response.usage_metadata
        row["prompt_tokens"] = usage.prompt_token_count if usage else None
        # Both billed at the OUTPUT price, and thinking is invisible in the
        # answer -- so they are what turns token counts into a cost per call.
        row["output_tokens"] = usage.candidates_token_count if usage else None
        row["thinking_tokens"] = usage.thoughts_token_count if usage else None
        try:
            parsed = response.parsed
            if not isinstance(parsed, MealAnalysis):
                parsed = MealAnalysis.model_validate_json(response.text or "")
        except Exception as exc:
            row["error"] = f"unparseable: {exc!s:.80}"
            return row
        row.update(
            error="",
            kcal_low=round(parsed.calories.low),
            kcal=round(parsed.calories.estimate),
            kcal_high=round(parsed.calories.high),
            protein=round(parsed.protein.estimate),
            confidence=parsed.confidence,
            items=len(parsed.items),
        )
        return row
    row["attempts"] = MAX_ATTEMPTS
    return row


def summarise(rows: list[dict], baseline: tuple[str, str]) -> None:
    """Per meal: each variant's mean against the baseline's, beside the noise."""
    groups: dict[tuple[str, str, str], list[dict]] = {}
    for row in rows:
        if row.get("error") or row.get("kcal") in (None, ""):
            continue
        key = (row["meal"], row["model"], row["variant"])
        groups.setdefault(key, []).append(row)

    def stats(key):
        found = groups.get(key, [])
        kcals = [float(r["kcal"]) for r in found]
        if not kcals:
            return None
        widths = [float(r["kcal_high"]) - float(r["kcal_low"]) for r in found]
        tokens = [int(r["prompt_tokens"]) for r in found if r.get("prompt_tokens")]
        return {
            "n": len(kcals),
            "mean": statistics.fmean(kcals),
            "spread": max(kcals) - min(kcals),
            "width": statistics.fmean(widths),
            "tokens": round(statistics.fmean(tokens)) if tokens else None,
        }

    meals = sorted({key[0] for key in groups})
    others = sorted({key[1:] for key in groups} - {baseline})
    print(f"\nBaseline: model={baseline[0]} variant={baseline[1]}")
    print(
        f"{'meal':<16}{'model/variant':<30}{'n':>3}{'kcal':>7}{'Δ':>7}"
        f"{'Δ%':>7}{'noise':>7}{'within':>8}{'width':>7}{'tokens':>8}"
    )
    verdicts: dict[tuple[str, str], list[tuple[float, bool, float]]] = {}
    for meal in meals:
        base = stats((meal, *baseline))
        if base is None:
            continue
        print(
            f"{meal:<16}{'/'.join(baseline):<30}{base['n']:>3}"
            f"{base['mean']:>7.0f}{'':>7}{'':>7}{base['spread']:>7.0f}{'':>8}"
            f"{base['width']:>7.0f}{base['tokens'] or '':>8}"
        )
        for other in others:
            got = stats((meal, *other))
            if got is None:
                continue
            delta = got["mean"] - base["mean"]
            pct = 100 * delta / base["mean"] if base["mean"] else 0.0
            # The larger of the two spreads: a delta inside either variant's own
            # repeat-to-repeat wobble is not evidence of a difference.
            noise = max(base["spread"], got["spread"])
            within = abs(delta) <= noise
            width_ratio = got["width"] / base["width"] if base["width"] else 1.0
            verdicts.setdefault(other, []).append((abs(pct), within, width_ratio))
            print(
                f"{'':<16}{'/'.join(other):<30}{got['n']:>3}{got['mean']:>7.0f}"
                f"{delta:>+7.0f}{pct:>+6.1f}%{got['spread']:>7.0f}"
                f"{'yes' if within else 'NO':>8}{got['width']:>7.0f}"
                f"{got['tokens'] or '':>8}"
            )

    print("\nPer variant, across meals:")
    for other, results in verdicts.items():
        pcts = [r[0] for r in results]
        print(
            f"  {'/'.join(other)}: meals={len(results)}  "
            f"median |Δ%|={statistics.median(pcts):.1f}  max |Δ%|={max(pcts):.1f}  "
            f"within noise={sum(r[1] for r in results)}/{len(results)}  "
            f"median range-width ratio={statistics.median(r[2] for r in results):.2f}"
        )


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--photos", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--variants", nargs="*", help="default: every subfolder")
    parser.add_argument("--models", nargs="*", default=[meal_ai.DEFAULT_MODEL])
    parser.add_argument("--baseline", default="original", help="baseline variant")
    parser.add_argument("--repeats", type=int, default=2)
    parser.add_argument("--pause", type=float, default=6.0, help="seconds between calls")
    parser.add_argument("--resume", action="store_true", help="skip rows already in --out")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    variants = args.variants or sorted(p.name for p in args.photos.iterdir() if p.is_dir())
    baseline = (args.models[0], args.baseline)

    done: list[dict] = []
    if args.out.exists() and (args.resume or args.summary_only):
        with args.out.open() as handle:
            done = list(csv.DictReader(handle))
    if args.summary_only:
        summarise(done, baseline)
        return
    finished = {
        (r["meal"], r["variant"], r["model"], r["repeat"])
        for r in done if not r.get("error")
    }

    by_variant = {v: photos_by_meal(args.photos / v) for v in variants}
    meals = sorted(set.intersection(*(set(m) for m in by_variant.values())))
    if not meals:
        sys.exit("No meal appears under the same name in every variant folder.")

    # Interleaved: every meal and variant once, then the second repeat. A model
    # that slows or degrades during the run then affects all variants alike
    # instead of whichever one happened to run last.
    plan = [
        (repeat, meal, variant, model)
        for repeat in range(1, args.repeats + 1)
        for meal in meals
        for variant in variants
        for model in args.models
        if (meal, variant, model, str(repeat)) not in finished
    ]
    print(f"{len(meals)} meals x {len(variants)} variants x {len(args.models)} models "
          f"x {args.repeats} repeats: {len(plan)} calls to make")

    rows = [r for r in done if not r.get("error")]
    # Always rewritten under the current header, finished rows first. Appending
    # to a file written by an older version of this script would put new columns
    # under old headings and shift every value silently.
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})
        for index, (repeat, meal, variant, model) in enumerate(plan, 1):
            try:
                row = await estimate(model, by_variant[variant][meal])
            except DailyQuotaReached as exc:
                print(f"\nSTOPPED: daily quota reached ({exc}).\n"
                      "Everything so far is saved; finish after midnight Pacific "
                      "with --resume.")
                break
            row.update(meal=meal, variant=variant, model=model, repeat=repeat)
            writer.writerow({field: row.get(field, "") for field in FIELDS})
            handle.flush()
            rows.append({k: str(v) for k, v in row.items()})
            print(f"[{index}/{len(plan)}] {meal} {variant} {model} r{repeat}: "
                  f"{row.get('kcal', '-')} kcal, {row.get('prompt_tokens', '-')} tokens, "
                  f"{row.get('seconds', '-')}s {row.get('error') or ''}")
            if index < len(plan):
                await asyncio.sleep(args.pause)

    summarise(rows, baseline)


if __name__ == "__main__":
    asyncio.run(main())
