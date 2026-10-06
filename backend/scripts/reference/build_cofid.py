"""Build app/data/reference/cofid.csv from the UK's CoFID workbook.

    venv/bin/python scripts/reference/build_cofid.py \\
        McCance_Widdowsons_Composition_of_Foods_Integrated_Dataset_2021..xlsx

Source: McCance and Widdowson's The Composition of Foods Integrated Dataset
2021, Public Health England, https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid
Licence: Open Government Licence v3.0. Attribution required (NOTICE.md).
Built 2026-10-06 from:
  436e9445ef2adb2a75f3d7edd51302de3adad25385f9795fc94ba58bd030e97d

Read from sheet "1.3 Proximates", ~2,900 foods commonly eaten in the UK.
Rows start under three header rows (name, code, label).

* Carbohydrate is CoFID's CHO, already "available" (fibre excluded), so it is
  taken as published. It is expressed as monosaccharide equivalents, which
  reads a few percent higher than the weight of starch eaten; a documented
  CoFID convention, left as is.
* Fibre is AOAC fibre where present, else NSP (Englyst). It is written for
  reference only, since nothing is subtracted.
* "Tr" is a trace (0), "N" is not measured (blank); see common.parse_value.
"""
import sys
from pathlib import Path

import openpyxl
from common import Row, parse_value, write

SHEET = "1.3 Proximates"
COLUMNS = {
    "code": "Food Code",
    "name": "Food Name",
    "protein": "Protein (g)",
    "fat": "Fat (g)",
    "carbs": "Carbohydrate (g)",
    "kcal": "Energy (kcal) (kcal)",
    "aoac": "AOAC fibre (g)",
    "nsp": "NSP (g)",
}


def read(path: Path) -> list[Row]:
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows_in = workbook[SHEET].iter_rows(values_only=True)
    header = [str(c).strip() if c is not None else "" for c in next(rows_in)]
    at = {key: header.index(label) for key, label in COLUMNS.items()}

    rows = []
    for cells in rows_in:
        code = cells[at["code"]]
        if not code:
            continue  # the two code/label rows under the header
        fibre = parse_value(cells[at["aoac"]])
        if fibre is None:
            fibre = parse_value(cells[at["nsp"]])
        rows.append(Row(
            source_id=str(code).strip(),
            name=str(cells[at["name"]]).strip(),
            calories=parse_value(cells[at["kcal"]]),
            protein=parse_value(cells[at["protein"]]),
            carbs=parse_value(cells[at["carbs"]]),
            fat=parse_value(cells[at["fat"]]),
            fibre=fibre,
        ))
    print(f"{path.name}: {len(rows)} foods")
    return rows


if __name__ == "__main__":
    write("cofid", read(Path(sys.argv[1])))
