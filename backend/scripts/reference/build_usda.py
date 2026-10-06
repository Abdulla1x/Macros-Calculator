"""Build app/data/reference/usda.csv from USDA FoodData Central's CSV downloads.

    venv/bin/python scripts/reference/build_usda.py \\
        FoodData_Central_foundation_food_csv_2026-04-30.zip \\
        FoodData_Central_sr_legacy_food_csv_2018-04.zip \\
        FoodData_Central_survey_food_csv_2024-10-31.zip

Source: https://fdc.nal.usda.gov/download-datasets/ (no key needed).
Licence: public domain (CC0 1.0); USDA asks for, but does not require, a citation.
Built 2026-10-06 from:
  70457ee9d9342f43bda2010318c85f04210c689fdeb9cd2da4c513b0e8dbc655  foundation 2026-04-30
  b80817294b8850530aaedf2e515c02593b1824f763a0ff356e5c2081643e6fd0  sr_legacy 2018-04
  5ccc25ec2777a8982fbb61378a42f415316173eb11e48c9a8ba4cb19f5a4f29c  survey (FNDDS) 2024-10-31

Three of FoodData Central's five data types, the generic ones. Branded is left
out on purpose: it is US packaged goods, which Open Food Facts already covers,
and its 400k rows would bury plain ingredients. Experimental is research data.

* Foundation: newest, lab-analysed, ~470 foods. Its food.csv also carries the
  lab's samples and sub-samples, which are not foods; only `foundation_food`
  rows are kept. It often lacks the classic kcal figure (1008) and has Atwater
  energy instead (2047 general, 2048 specific).
* SR Legacy: the classic reference list, frozen in 2018, ~7,800 foods.
* Survey (FNDDS): foods as people report eating them ("Apple, raw"), ~5,400.

Where two of them name the same food, the earlier one wins, in that order.
"""
import csv
import io
import re
import sys
import zipfile
from pathlib import Path

from common import Row, available_carbs, write

KEEP = ("foundation_food", "sr_legacy_food", "survey_fndds_food")

ENERGY = (1008, 2047, 2048)  # kcal, then Atwater general, then specific
PROTEIN, FAT = 1003, 1004
CARBS = (1005, 1050)  # by difference, then by summation
FIBRE = (1079, 2033)  # total dietary, then AOAC 2011.25
WANTED = {*ENERGY, PROTEIN, FAT, *CARBS, *FIBRE}

# SR Legacy appends "(Includes foods for USDA's Food Distribution Program)" to
# ~100 names. It is about a federal programme, not the food, and it would make
# "Apples, raw, with skin" read as a different food from its FNDDS twin.
PROGRAMME_NOTE = re.compile(r"\s*\((?:includes foods for usda|includes usda)[^)]*\)", re.I)


def _rows(zf: zipfile.ZipFile, name: str):
    member = next(m for m in zf.namelist() if m.endswith("/" + name))
    with zf.open(member) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8"))


def _first(values: dict[int, float], ids) -> float | None:
    return next((values[i] for i in ids if i in values), None)


def read(path: Path) -> list[Row]:
    with zipfile.ZipFile(path) as zf:
        foods = {
            row["fdc_id"]: row["description"]
            for row in _rows(zf, "food.csv")
            if row["data_type"] in KEEP
        }
        # ⚠️ FNDDS's food_nutrient.csv puts the legacy nutrient NUMBER (208
        # for kcal) in the nutrient_id column, where the other two datasets
        # put the id (1008). Without this translation every FNDDS food reads
        # as having no kcal and is dropped. The ranges cannot collide: ids
        # start at 1001, numbers stop below 1000.
        by_number = {
            row["nutrient_nbr"]: int(row["id"])
            for row in _rows(zf, "nutrient.csv")
            if row["nutrient_nbr"]
        }
        nutrients: dict[str, dict[int, float]] = {}
        for row in _rows(zf, "food_nutrient.csv"):
            raw_id = row["nutrient_id"]
            nutrient = int(raw_id) if int(raw_id) >= 1000 else by_number.get(raw_id, 0)
            if row["fdc_id"] in foods and nutrient in WANTED and row["amount"]:
                nutrients.setdefault(row["fdc_id"], {})[nutrient] = float(row["amount"])

    rows = []
    for fdc_id, description in foods.items():
        values = nutrients.get(fdc_id, {})
        fibre = _first(values, FIBRE)
        rows.append(Row(
            source_id=fdc_id,
            name=PROGRAMME_NOTE.sub("", description).strip(),
            calories=_first(values, ENERGY),
            protein=values.get(PROTEIN),
            carbs=available_carbs(_first(values, CARBS), fibre),
            fat=values.get(FAT),
            fibre=fibre,
        ))
    print(f"{path.name}: {len(rows)} foods")
    return rows


def main(paths: list[str]) -> None:
    order = {"foundation": 0, "sr_legacy": 1, "survey": 2}
    paths = sorted(paths, key=lambda p: next(v for k, v in order.items() if k in Path(p).name))
    rows = [row for path in paths for row in read(Path(path))]
    write("usda", rows)


if __name__ == "__main__":
    main(sys.argv[1:])
