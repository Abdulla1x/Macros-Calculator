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

**Reference mode (--manifest).** The questions above ask whether a variant
CHANGES the answer. Choosing a model also needs to know whether it is RIGHT, so
a manifest CSV (meal, photos, set, note, ref_kcal, ref_protein, photo_ok) names each meal's
photos (";"-separated, several views of one meal), the note the user typed, and
a reference value. Each meal is sent in two conditions -- `photo` alone, and
`note` (the photos plus the user's own words) -- and the summary reports the
error against the reference and how often the reference fell inside the stated
range. `set` says what the reference is: T, logged from the saved library with
no AI (a true value), or R, the value the user saved from an earlier AI estimate
(so biased toward the model that made it, and reported apart from T).

A refusal for the DAY retires that model for the rest of the run (see
DailyQuotaReached); the other models carry on, since each has its own quota.

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

from app.routers.ai import MAX_IMAGES  # noqa: E402  (a test may not send more than the app does)
from app.schemas import MealAnalysis  # noqa: E402
from app.services import meal_ai  # noqa: E402

MIME = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
}
FIELDS = [
    "meal", "variant", "model", "repeat", "bytes", "prompt_tokens",
    "output_tokens", "thinking_tokens",
    "kcal_low", "kcal", "kcal_high", "protein_low", "protein", "protein_high",
    "confidence", "items", "seconds", "attempts", "error",
]
# Reference mode's two conditions, carried in the `variant` column.
CONDITIONS = ("photo", "note")
# Overload (503) and per-minute limits (429) are routine on the free tier.
# Waiting them out is what the app does too; a give-up here is recorded as an
# error row and skipped by the summary, never counted as an estimate.
#
# Two, not more: a failed attempt counts against the per-day quota exactly like
# a successful one (measured 2026-10-04), so every retry is one fewer estimate
# the day can buy. A row given up on is finished with --resume another day.
MAX_ATTEMPTS = 2
RETRY_WAIT_S = 15
RATE_LIMIT_WAIT_S = 65

# Paid-tier list prices per 1M tokens (input, output), read 2026-10-04 from
# ai.google.dev/gemini-api/docs/pricing. Thinking tokens are billed as output.
# The 3.6-3.8 Flash prices double on 2027-01-01, hence two columns.
PRICES_2026 = {
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.6-flash": (0.75, 3.75),
    "gemini-3.7-flash": (0.75, 3.75),
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-2.5-flash": (0.30, 2.50),
}
PRICES_2027 = {
    **PRICES_2026,
    "gemini-3.6-flash": (1.50, 7.50),
    "gemini-3.7-flash": (1.50, 7.50),
    "gemini-3.8-flash": (1.50, 7.50),
}


class DailyQuotaReached(Exception):
    """Google refused for the DAY, not the minute: stop, don't retry.

    Retrying a per-day refusal cannot succeed before midnight Pacific, and on a
    key shared with production every extra call is one more the app's users
    cannot make. Per-minute refusals carry a different quota id and are waited
    out like overload.
    """


# One definition of "per day", shared with the app: the structured quotaId, never
# the message text (meal_ai.quota_ids says why).
quota_ids = meal_ai.quota_ids
is_daily_quota = meal_ai.is_daily_quota


def photos_by_meal(variant_dir: Path) -> dict[str, Path]:
    return {
        path.stem: path
        for path in sorted(variant_dir.iterdir())
        if path.suffix.lower() in MIME
    }


async def estimate(model: str, photos: list[Path], text: str | None = None) -> dict:
    images = [(p.read_bytes(), MIME[p.suffix.lower()]) for p in photos]
    contents = meal_ai._build_contents(images, text, None)
    config = meal_ai.analysis_config(
        types.HttpOptions(timeout=meal_ai.ANALYZE_TIMEOUT_MS)
    )
    row: dict = {"bytes": sum(len(data) for data, _ in images)}
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
            protein_low=round(parsed.protein.low),
            protein=round(parsed.protein.estimate),
            protein_high=round(parsed.protein.high),
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


def load_manifest(path: Path) -> dict[str, dict]:
    """Meals the owner confirmed; anything not T or R is left out."""
    with path.open() as handle:
        return {
            row["meal"]: row
            for row in csv.DictReader(handle)
            if row.get("set") in ("T", "R") and row.get("ref_kcal")
        }


def against_reference(rows: list[dict], manifest: dict[str, dict]) -> None:
    """Error against the reference, and whether the stated range held it.

    Per model, condition and reference set. Each meal counts once: its repeats
    are averaged first, so a meal answered twice does not outweigh one answered
    once. Coverage is per call, because a range is what each single answer
    claims. Signed error is printed beside the absolute, since a model that is
    always 20% low is a different problem from one that scatters.
    """
    groups: dict[tuple[str, str, str], dict[str, list[dict]]] = {}
    for row in rows:
        ref = manifest.get(row["meal"])
        if ref is None or row.get("error") or row.get("kcal") in (None, ""):
            continue
        key = (row["model"], row["variant"], ref["set"])
        groups.setdefault(key, {}).setdefault(row["meal"], []).append(row)

    print("\nAgainst the reference (meals averaged over repeats; coverage per call):")
    print(f"{'model':<24}{'cond':<7}{'set':<4}{'meals':>6}{'|err| kcal':>11}"
          f"{'bias':>7}{'|err| prot':>11}{'kcal in range':>14}{'prot in range':>14}"
          f"{'width':>7}{'noise':>7}")
    for (model, condition, ref_set), by_meal in sorted(groups.items()):
        errors, biases, protein_errors, spreads = [], [], [], []
        hits = protein_hits = calls = 0
        widths = []
        for meal, found in by_meal.items():
            ref_kcal = float(manifest[meal]["ref_kcal"])
            ref_protein = float(manifest[meal]["ref_protein"] or 0)
            kcals = [float(r["kcal"]) for r in found]
            mean = statistics.fmean(kcals)
            if len(kcals) > 1:
                spreads.append((max(kcals) - min(kcals)) / ref_kcal * 100)
            errors.append(abs(mean - ref_kcal) / ref_kcal * 100)
            biases.append((mean - ref_kcal) / ref_kcal * 100)
            if ref_protein:
                protein_mean = statistics.fmean(float(r["protein"]) for r in found)
                protein_errors.append(abs(protein_mean - ref_protein) / ref_protein * 100)
            for r in found:
                calls += 1
                hits += float(r["kcal_low"]) <= ref_kcal <= float(r["kcal_high"])
                if r.get("protein_low") not in (None, ""):
                    protein_hits += (
                        float(r["protein_low"]) <= ref_protein <= float(r["protein_high"])
                    )
                widths.append((float(r["kcal_high"]) - float(r["kcal_low"])) / ref_kcal * 100)
        protein = f"{statistics.median(protein_errors):>10.1f}%" if protein_errors else f"{'-':>11}"
        print(f"{model:<24}{condition:<7}{ref_set:<4}{len(by_meal):>6}"
              f"{statistics.median(errors):>10.1f}%{statistics.median(biases):>+6.0f}%"
              f"{protein}{hits:>9}/{calls:<4}{protein_hits:>9}/{calls:<4}"
              f"{statistics.median(widths):>6.0f}%"
              + (f"{statistics.median(spreads):>6.1f}%" if spreads else f"{'-':>7}"))


def per_model(rows: list[dict], all_rows: list[dict]) -> None:
    """Latency, tokens and cost per call, per model: what a model choice costs.

    Seconds are for one answered attempt, so they compare with each other, not
    with production's provider_ms -- that one includes retries and backoff.
    Failures are counted from every row written, since an overloaded model is
    a finding too.
    """
    print("\nPer model (answered calls; medians):")
    print(f"{'model':<24}{'ok':>4}{'fail':>5}{'sec':>6}{'in':>6}{'out':>6}"
          f"{'think':>7}{'¢ 2026':>8}{'¢ 2027':>8}")
    models = sorted({r["model"] for r in all_rows})
    for model in models:
        ok = [r for r in rows if r["model"] == model and not r.get("error")
              and r.get("kcal") not in (None, "")]
        failed = sum(1 for r in all_rows if r["model"] == model and r.get("error"))

        def median(field):
            values = [float(r[field]) for r in ok if r.get(field) not in (None, "")]
            return statistics.median(values) if values else None

        seconds, tokens_in = median("seconds"), median("prompt_tokens")
        tokens_out, thinking = median("output_tokens"), median("thinking_tokens")

        def cents(prices):
            if model not in prices or None in (tokens_in, tokens_out):
                return None
            price_in, price_out = prices[model]
            billed_out = tokens_out + (thinking or 0)
            return 100 * (tokens_in * price_in + billed_out * price_out) / 1e6

        def show(value, width, digits=0):
            return f"{value:>{width}.{digits}f}" if value is not None else f"{'-':>{width}}"

        print(f"{model:<24}{len(ok):>4}{failed:>5}{show(seconds, 6, 1)}"
              f"{show(tokens_in, 6)}{show(tokens_out, 6)}{show(thinking, 7)}"
              f"{show(cents(PRICES_2026), 8, 2)}{show(cents(PRICES_2027), 8, 2)}")


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
    parser.add_argument(
        "--manifest", type=Path,
        help="reference mode: CSV of confirmed meals; --photos is then one folder "
             "of shrunk photos, found by file stem",
    )
    parser.add_argument("--conditions", nargs="*", default=list(CONDITIONS),
                        choices=CONDITIONS, help="reference mode only")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest) if args.manifest else None
    if manifest is not None:
        variants = args.conditions
        baseline = (args.models[0], "photo")
    else:
        variants = args.variants or sorted(p.name for p in args.photos.iterdir() if p.is_dir())
        baseline = (args.models[0], args.baseline)

    def report(rows: list[dict], attempted: list[dict]) -> None:
        if manifest is not None:
            against_reference(rows, manifest)
        else:
            summarise(rows, baseline)
        per_model(rows, attempted)

    done: list[dict] = []
    if args.out.exists() and (args.resume or args.summary_only):
        with args.out.open() as handle:
            done = list(csv.DictReader(handle))
    if args.summary_only:
        report([r for r in done if not r.get("error")], done)
        return
    finished = {
        (r["meal"], r["variant"], r["model"], r["repeat"])
        for r in done if not r.get("error")
    }

    if manifest is not None:
        shrunk = photos_by_meal(args.photos)

        def inputs(meal: str, condition: str) -> tuple[list[Path], str | None] | None:
            entry = manifest[meal]
            note = (entry.get("note") or "").strip() or None
            if condition == "note" and note is None:
                return None  # nothing to add to the photo: same as `photo`
            if condition == "photo" and entry.get("photo_ok") == "no":
                # The logged meal holds things the photos do not show (bread
                # off-camera, a topping added later): photo-only would be
                # scored against food the model was never shown.
                return None
            stems = [Path(name).stem for name in entry["photos"].split(";") if name]
            if len(stems) > MAX_IMAGES:
                sys.exit(f"{meal}: {len(stems)} photos, but the app sends at most "
                         f"{MAX_IMAGES} (MAX_IMAGES)")
            missing = [stem for stem in stems if stem not in shrunk]
            if missing:
                sys.exit(f"{meal}: no shrunk photo for {missing} in {args.photos}")
            return [shrunk[stem] for stem in stems], (note if condition == "note" else None)

        meals = sorted(manifest)
    else:
        by_variant = {v: photos_by_meal(args.photos / v) for v in variants}

        def inputs(meal: str, variant: str) -> tuple[list[Path], str | None] | None:
            return [by_variant[variant][meal]], None

        meals = sorted(set.intersection(*(set(m) for m in by_variant.values())))
    if not meals:
        sys.exit("No meal to run.")

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
        and inputs(meal, variant) is not None
    ]
    print(f"{len(meals)} meals x {len(variants)} variants x {len(args.models)} models "
          f"x {args.repeats} repeats: {len(plan)} calls to make")

    rows = [r for r in done if not r.get("error")]
    attempted = list(done)
    # Models Google has refused for the day. Each model has its own per-day
    # quota, so one running out is no reason to stop measuring the others.
    exhausted: set[str] = set()
    # Always rewritten under the current header, finished rows first. Appending
    # to a file written by an older version of this script would put new columns
    # under old headings and shift every value silently.
    with args.out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDS})
        for index, (repeat, meal, variant, model) in enumerate(plan, 1):
            if model in exhausted:
                continue
            try:
                photos, text = inputs(meal, variant)
                row = await estimate(model, photos, text)
            except DailyQuotaReached as exc:
                exhausted.add(model)
                print(f"\n{model}: daily quota reached ({exc}). Skipping it for "
                      "the rest of this run; finish after midnight Pacific with "
                      "--resume.\n")
                continue
            row.update(meal=meal, variant=variant, model=model, repeat=repeat)
            writer.writerow({field: row.get(field, "") for field in FIELDS})
            handle.flush()
            # The same shape csv.DictReader gives a resumed row: a missing
            # value is "", never the string "None" (Flash-Lite and Gemma
            # report no thinking tokens at all).
            rows.append({k: "" if v is None else str(v) for k, v in row.items()})
            attempted.append(rows[-1])
            print(f"[{index}/{len(plan)}] {meal} {variant} {model} r{repeat}: "
                  f"{row.get('kcal', '-')} kcal, {row.get('prompt_tokens', '-')} tokens, "
                  f"{row.get('seconds', '-')}s {row.get('error') or ''}")
            if index < len(plan):
                await asyncio.sleep(args.pause)

    report(rows, attempted)


if __name__ == "__main__":
    asyncio.run(main())
