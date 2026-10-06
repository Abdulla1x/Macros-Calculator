# Food data sources

The CSVs in this folder are extracts of open national food-composition tables,
built by the scripts in `backend/scripts/reference/`. The app searches them
(`app/reference_foods.py`) so a user can log a generic food without typing its
macros in by hand.

**What was changed in every table:** only energy (kcal), protein, carbohydrate,
fat and fibre are kept, per 100 g. **Carbohydrate excludes fibre** in every
file; where a table publishes carbohydrate including fibre, the fibre was
subtracted. Names were lightly cleaned (whitespace, programme notes). Foods
without energy or protein were left out, and a food named identically in two
of a table's datasets is kept once.

## USDA FoodData Central — `usda.csv`

U.S. Department of Agriculture, Agricultural Research Service. FoodData Central.
Foundation Foods (2026-04-30), SR Legacy (2018-04) and Food and Nutrient
Database for Dietary Studies / Survey (2024-10-31).
https://fdc.nal.usda.gov/

Public domain under CC0 1.0. USDA requests, but does not require, this citation.
Carbohydrate (by difference) has had total dietary fibre subtracted.
