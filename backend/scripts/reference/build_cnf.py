"""Build app/data/reference/cnf.csv from the Canadian Nutrient File 2015.

    venv/bin/python scripts/reference/build_cnf.py cnf-fcen-csv.zip

Source: Canadian Nutrient File, Health Canada, 2015.
https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data/canadian-nutrient-file-2015-download-files.html
Licence: Open Government Licence - Canada; Health Canada must be identified
as the source (NOTICE.md).
Built 2026-10-06 from:
  fb77503d88186844cc2c27b39432d755505f97a789c97fc5973a30d0cd4b0367

Only the base zip is read. The separate "update" zip
(cnf-fcen-csv-update-miseajour.zip) is NOT a delta to apply on top: it is
the change log that produced 2015 and is already in the base. Checked
2026-10-06: 603 of its 607 added foods are in the base, none of its 584
deleted foods are, and 99.8% of its changed nutrient values already match.

* Nutrient ids are the old USDA numbers: 208 kcal, 203 protein, 204 fat,
  205 carbohydrate (total, by difference, so WITH fibre), 291 fibre. Fibre is
  subtracted, as for USDA.
* Much of CNF is copied from USDA's SR Legacy. A food whose normalized name
  equals a usda.csv name is left out here; search would show only USDA's row
  anyway (same name, higher priority), so keeping it only costs memory.
  Build usda.csv first.
* Names are Latin-1 in the CSVs, English in FoodDescription.
"""
import csv
import io
import sys
import zipfile
from pathlib import Path

from common import Row, available_carbs, normalize, write

from app.reference_foods import DATA_DIR

KCAL, PROTEIN, FAT, CARBS, FIBRE = "208", "203", "204", "205", "291"
WANTED = {KCAL, PROTEIN, FAT, CARBS, FIBRE}


def _rows(zf: zipfile.ZipFile, name: str, encoding: str):
    yield from csv.DictReader(io.StringIO(zf.read(name).decode(encoding)))


def read(path: Path) -> list[Row]:
    with zipfile.ZipFile(path) as zf:
        foods = {r["FoodID"]: r["FoodDescription"] for r in _rows(zf, "FOOD NAME.csv", "latin-1")}
        values: dict[str, dict[str, float]] = {}
        for r in _rows(zf, "NUTRIENT AMOUNT.csv", "utf-8"):
            if r["NutrientID"] in WANTED and r["NutrientValue"].strip():
                values.setdefault(r["FoodID"], {})[r["NutrientID"]] = float(r["NutrientValue"])

    with (DATA_DIR / "usda.csv").open(newline="", encoding="utf-8") as handle:
        usda_names = {normalize(r["name"]) for r in csv.DictReader(handle)}

    rows, copies = [], 0
    for food_id, name in foods.items():
        if normalize(name) in usda_names:
            copies += 1
            continue
        v = values.get(food_id, {})
        fibre = v.get(FIBRE)
        rows.append(Row(
            source_id=food_id,
            name=name,
            calories=v.get(KCAL),
            protein=v.get(PROTEIN),
            carbs=available_carbs(v.get(CARBS), fibre),
            fat=v.get(FAT),
            fibre=fibre,
        ))
    print(f"{path.name}: {len(foods)} foods, {copies} left out as USDA copies")
    return rows


if __name__ == "__main__":
    write("cnf", read(Path(sys.argv[1])))
