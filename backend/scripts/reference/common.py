"""Shared by the build_<source>.py scripts: one row shape, one writer.

Each build script turns one national table's download into
app/data/reference/<source>.csv, the file app/reference_foods.py searches.
Run them from backend/, e.g. `venv/bin/python scripts/reference/build_usda.py
<zip> ...`; the raw downloads stay outside the repo, and each script's
docstring records where they came from and the SHA-256 they were built from.

The rules every table follows, so the five files mean the same thing:

* Per 100 g, always.
* **Carbs EXCLUDE fibre** ("available carbohydrate"), owner's decision
  2026-10-06. Three of the five tables publish it that way; USDA and CNF
  publish carbs *with* fibre and have it subtracted. Fibre is written in its
  own column, so switching definition later is a change to `available_carbs`
  and a re-run, not a re-download.
* A row without kcal or protein is dropped: those are the two numbers the app
  cannot log without.
* Trace values become 0 and unmeasured ones stay blank; the per-table parsers
  decide which spelling means which.
"""
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.reference_foods import DATA_DIR, normalize  # noqa: E402

COLUMNS = ("source_id", "name", "calories", "protein", "carbs", "fat", "fibre")


@dataclass
class Row:
    source_id: str
    name: str
    calories: float | None
    protein: float | None
    carbs: float | None
    fat: float | None
    fibre: float | None


def available_carbs(total: float | None, fibre: float | None) -> float | None:
    """Carbs with fibre -> carbs without, never below zero.

    With no fibre figure there is nothing to subtract, so the total stands;
    that overstates carbs by the fibre content, which for the foods missing it
    is small. The zero floor applies either way: USDA's carbohydrate "by
    difference" is 100 minus everything else measured, and on meat and fish
    that comes out slightly NEGATIVE (-0.43 g for raw chicken breast).
    Uncorrected, saving such a row to the library would be refused, because
    foods.carbs must be >= 0."""
    if total is None:
        return None
    return max(total - (fibre or 0.0), 0.0)


def _format(value: float | None) -> str:
    # Two decimals is finer than any of these tables measures; :g drops the
    # trailing zeros so the file stays small and diffs stay readable.
    return "" if value is None else f"{round(value, 2):g}"


def write(source: str, rows: list[Row]) -> Path:
    """Drop unusable rows, keep the first of any repeated name, sort by id.

    The caller orders `rows` by preference, so "first" is a decision it made.
    Sorting by source_id afterwards keeps a re-run's diff to real changes."""
    kept: dict[str, Row] = {}
    dropped = 0
    for row in rows:
        if row.calories is None or row.protein is None or not row.name.strip():
            dropped += 1
            continue
        kept.setdefault(normalize(row.name), row)
    path = DATA_DIR / f"{source}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for row in sorted(kept.values(), key=lambda r: r.source_id):
            writer.writerow([
                row.source_id, row.name.strip(),
                *(_format(v) for v in (row.calories, row.protein, row.carbs, row.fat, row.fibre)),
            ])
    duplicates = len(rows) - dropped - len(kept)
    print(f"{source}: {len(kept)} rows written to {path} "
          f"({dropped} without kcal/protein, {duplicates} repeated names)")
    return path
