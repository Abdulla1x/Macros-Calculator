"""Checks on the committed tables in app/data/reference/, not on fixtures.

These run against the real files, so a rebuilt table or a ranking change that
makes the search worse fails CI rather than reaching the autocomplete."""
import csv
import sys
from pathlib import Path

import pytest

from app import reference_foods

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "reference"))

COLUMNS = ["source_id", "name", "calories", "protein", "carbs", "fat", "fibre"]
TABLES = sorted(reference_foods.DATA_DIR.glob("*.csv"))


@pytest.fixture(autouse=True)
def _real_tables():
    reference_foods.clear_cache()
    yield
    reference_foods.clear_cache()


def test_every_committed_table_is_a_known_source():
    assert TABLES, "no reference tables committed"
    assert {path.stem for path in TABLES} <= set(reference_foods.SOURCES)


@pytest.mark.parametrize("path", TABLES, ids=lambda p: p.stem)
def test_every_row_is_well_formed(path):
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == COLUMNS
        ids = set()
        for row in reader:
            assert row["name"].strip(), row
            assert row["source_id"] not in ids, row
            ids.add(row["source_id"])
            assert row["calories"] and row["protein"], row
            for column in COLUMNS[2:]:
                if row[column]:
                    assert float(row[column]) >= 0, row


def test_the_ranking_meets_the_agreed_bar():
    from ranking_report import PASS_BAR, evaluate

    assert evaluate() >= PASS_BAR
