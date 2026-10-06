"""Build app/data/reference/ciqual.csv from France's Ciqual table (English).

    venv/bin/python scripts/reference/build_ciqual.py \\
        "Table Ciqual 2025_ENG_2025_11_03.xlsx"

Source: Anses. 2025. Table de composition nutritionnelle des aliments Ciqual.
https://ciqual.anses.fr/ (download page: /cms/en/node/19).
Licence: Licence Ouverte (Etalab), per the site's legal notice: reuse is free
with an explicit reference to the source, and must not suggest that ANSES
endorses the reuse. Attribution in NOTICE.md; the ANSES logo is never used.
Built 2026-10-06 from:
  021d80f202fa184d7d1e6c6283da7d94a408fef0fbca0c28293243673c0778b0

3,484 foods representative of what is eaten in France, with English names.

* Energy is the EU Regulation 1169/2011 kcal column, the one on EU labels.
* Carbohydrate is Ciqual's "Carbohydrate", available carbohydrate (fibre
  excluded), taken as published.
* Values are text with decimal commas; "-" is not measured, "traces" and
  "< 0,2" are traces (see common.parse_value).
* Group "00" holds category averages ("Dessert (average)"), which are not
  foods anyone eats and are left out.
"""
import sys
from pathlib import Path

import openpyxl
from common import Row, parse_value, write


def _label(cell) -> str:
    # Headers are wrapped across lines: "Energy,\nRegulation\nEU No\n1169\n...".
    return " ".join(str(cell or "").split())


COLUMNS = {
    "group": "alim_grp_code",
    "code": "alim_code",
    "name": "alim_nom_eng",
    "kcal": "Energy, Regulation EU No 1169 2011 (kcal 100g)",
    "protein": "Protein (g 100g)",
    "carbs": "Carbohydrate (g 100g)",
    "fat": "Fat (g 100g)",
    "fibre": "Fibres (g 100g)",
}


def read(path: Path) -> list[Row]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows_in = workbook["food composition"].iter_rows(values_only=True)
    header = [_label(c).replace("/", " ") for c in next(rows_in)]
    header = [" ".join(h.split()) for h in header]
    at = {key: header.index(label) for key, label in COLUMNS.items()}

    rows = []
    for cells in rows_in:
        if str(cells[at["group"]]).strip() == "00":
            continue
        rows.append(Row(
            source_id=str(cells[at["code"]]).strip(),
            name=str(cells[at["name"]] or "").strip(),
            calories=parse_value(cells[at["kcal"]]),
            protein=parse_value(cells[at["protein"]]),
            carbs=parse_value(cells[at["carbs"]]),
            fat=parse_value(cells[at["fat"]]),
            fibre=parse_value(cells[at["fibre"]]),
        ))
    print(f"{path.name}: {len(rows)} foods")
    return rows


if __name__ == "__main__":
    write("ciqual", read(Path(sys.argv[1])))
