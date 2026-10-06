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

## UK CoFID — `cofid.csv`

Contains public sector information licensed under the Open Government Licence
v3.0 (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
Source: Public Health England (2021). McCance and Widdowson's The Composition
of Foods Integrated Dataset 2021.
https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid

Carbohydrate is CoFID's available carbohydrate as published (monosaccharide
equivalents, which read a few percent above the weight of starch eaten).
CoFID 2021 gives two foods the code 13-669; the second is stored as 13-669#2.

## France Ciqual — `ciqual.csv`

Anses. 2025. Table de composition nutritionnelle des aliments Ciqual.
https://ciqual.anses.fr/ — reused under the Licence Ouverte
(https://www.etalab.gouv.fr/licence-ouverte-open-licence/). ANSES does not
endorse this app or its use of the data. English food names; energy is the EU
Regulation 1169/2011 figure; carbohydrate is Ciqual's available carbohydrate
as published. Category averages (group 00) were left out. Data as published on
2025-11-03.

## Australia AFCD — `afcd.csv`

Food Standards Australia New Zealand (2025). Australian Food Composition
Database - Release 3. Canberra: FSANZ.
https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd
Licensed under Creative Commons Attribution 2.5 Australia
(https://creativecommons.org/licenses/by/2.5/au/).

Changes: energy converted from kJ ("Energy with dietary fibre, equated") to
kcal by dividing by 4.184; carbohydrate is "Available carbohydrate, with sugar
alcohols" as published.

## Canada CNF — `cnf.csv`

Canadian Nutrient File, Health Canada, 2015. Licensed under the Open
Government Licence - Canada (https://open.canada.ca/en/open-government-licence-canada).
https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data.html

Changes: carbohydrate (total, by difference) has had total dietary fibre
subtracted; foods whose name is identical to a USDA food are left out, since
CNF copies many of them from USDA.
