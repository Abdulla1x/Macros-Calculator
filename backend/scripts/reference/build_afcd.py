"""Build app/data/reference/afcd.csv from the Australian Food Composition Database.

    venv/bin/python scripts/reference/build_afcd.py \\
        "AFCD Release 3 - Nutrient profiles.xlsx"

Source: Food Standards Australia New Zealand (2025). Australian Food
Composition Database - Release 3. Canberra: FSANZ.
https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd/data-files
Licence: Creative Commons Attribution 2.5 Australia (CC BY 2.5 AU).
Attribution and the changes made are in NOTICE.md.
Built 2026-10-06 from:
  14cb3e73dbf58987b440e6299624c0fefd7a4e61591fc1f753995d9534e0efc9

Sheet "All solids & liquids per 100 g", 1,588 foods. The header is the third
row, under a title and a blank line.

* Energy is published in kJ only. kcal = "Energy with dietary fibre, equated"
  / 4.184, the figure that counts fibre's energy, like the other tables.
* Carbohydrate is "Available carbohydrate, with sugar alcohols": fibre
  already excluded, taken as published.
"""
import sys
from pathlib import Path

import openpyxl
from common import Row, parse_value, write

SHEET = "All solids & liquids per 100 g"
KJ_PER_KCAL = 4.184
COLUMNS = {
    "key": "Public Food Key",
    "name": "Food Name",
    "kj": "Energy with dietary fibre, equated (kJ)",
    "protein": "Protein (g)",
    "fat": "Fat, total (g)",
    "fibre": "Total dietary fibre (g)",
    "carbs": "Available carbohydrate, with sugar alcohols (g)",
}


def read(path: Path) -> list[Row]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows_in = workbook[SHEET].iter_rows(values_only=True)
    next(rows_in), next(rows_in)  # title, blank
    header = [" ".join(str(c or "").split()) for c in next(rows_in)]
    at = {key: header.index(label) for key, label in COLUMNS.items()}

    rows = []
    for cells in rows_in:
        if not cells[at["key"]]:
            continue
        kj = parse_value(cells[at["kj"]])
        rows.append(Row(
            source_id=str(cells[at["key"]]).strip(),
            name=str(cells[at["name"]]).strip(),
            calories=None if kj is None else kj / KJ_PER_KCAL,
            protein=parse_value(cells[at["protein"]]),
            carbs=parse_value(cells[at["carbs"]]),
            fat=parse_value(cells[at["fat"]]),
            fibre=parse_value(cells[at["fibre"]]),
        ))
    print(f"{path.name}: {len(rows)} foods")
    return rows


if __name__ == "__main__":
    write("afcd", read(Path(sys.argv[1])))
