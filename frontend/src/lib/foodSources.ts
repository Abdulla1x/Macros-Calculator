/** Where a food's numbers came from, and how each source is named and credited.
 *
 * One module so the autocomplete's badges, the library's badges and the credits
 * block cannot drift apart. The values mirror the server's foods.source CHECK
 * (backend/app/models.py, migration 0018) and its ReferenceSource Literal.
 */

/** The imported national tables, in the server's tie-break order. */
export type ReferenceSource = 'usda' | 'cofid' | 'ciqual' | 'afcd' | 'cnf'

export type FoodSource = 'user' | 'openfoodfacts' | ReferenceSource

/** The short badge on a suggestion or a library row. A country code for the
 *  tables, because "where is this from" is the question the badge answers and
 *  "UK" says more to most people than "CoFID". */
export const SOURCE_BADGE: Record<FoodSource, string> = {
  user: 'yours',
  openfoodfacts: 'OFF',
  usda: 'USDA',
  cofid: 'UK',
  ciqual: 'FR',
  afcd: 'AU',
  cnf: 'CA',
}

/** The full name, for screen readers and the library's longer badge. */
export const SOURCE_NAME: Record<FoodSource, string> = {
  user: 'yours',
  openfoodfacts: 'Open Food Facts',
  usda: 'USDA FoodData Central',
  cofid: 'UK CoFID',
  ciqual: 'France Ciqual',
  afcd: 'Australia AFCD',
  cnf: 'Canada CNF',
}

/** A row's numbers are no longer the source's once the user changes one.
 *
 * The same rule the server applies on PUT (routers/foods.py:update_food): a
 * corrected figure is the user's own, so the badge must stop claiming a
 * provenance the numbers no longer have. A rename changes no number, so it
 * keeps the source. */
export const NUMBER_FIELDS = ['servingSize', 'calories', 'protein', 'carbs', 'fat'] as const

export function sourceAfterEdit(current: FoodSource, changedFields: readonly string[]): FoodSource {
  return changedFields.some((field) => (NUMBER_FIELDS as readonly string[]).includes(field))
    ? 'user'
    : current
}

export interface DataCredit {
  source: Exclude<FoodSource, 'user'>
  /** The attribution each licence asks for, as its publisher words it. */
  citation: string
  licence: string
  licenceUrl: string
  url: string
}

/** Shown on Settings → Library. Every licence here except USDA's requires the
 *  credit; backend/app/data/reference/NOTICE.md carries the same text plus
 *  what was changed. Ciqual's terms also require that nothing suggests ANSES
 *  endorses the app, hence that sentence in the block itself. */
export const DATA_CREDITS: DataCredit[] = [
  {
    source: 'usda',
    citation: 'U.S. Department of Agriculture, Agricultural Research Service. FoodData Central.',
    licence: 'Public domain (CC0 1.0)',
    licenceUrl: 'https://creativecommons.org/publicdomain/zero/1.0/',
    url: 'https://fdc.nal.usda.gov/',
  },
  {
    source: 'cofid',
    citation:
      "Public Health England (2021). McCance and Widdowson's The Composition of Foods Integrated Dataset 2021. Contains public sector information licensed under the Open Government Licence v3.0.",
    licence: 'Open Government Licence v3.0',
    licenceUrl: 'https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/',
    url: 'https://www.gov.uk/government/publications/composition-of-foods-integrated-dataset-cofid',
  },
  {
    source: 'ciqual',
    citation: 'Anses. 2025. Table de composition nutritionnelle des aliments Ciqual.',
    licence: 'Licence Ouverte',
    licenceUrl: 'https://www.etalab.gouv.fr/licence-ouverte-open-licence/',
    url: 'https://ciqual.anses.fr/',
  },
  {
    source: 'afcd',
    citation:
      'Food Standards Australia New Zealand (2025). Australian Food Composition Database – Release 3. Canberra: FSANZ.',
    licence: 'CC BY 2.5 AU',
    licenceUrl: 'https://creativecommons.org/licenses/by/2.5/au/',
    url: 'https://www.foodstandards.gov.au/science-data/food-nutrient-databases/afcd',
  },
  {
    source: 'cnf',
    citation: 'Canadian Nutrient File, Health Canada, 2015.',
    licence: 'Open Government Licence – Canada',
    licenceUrl: 'https://open.canada.ca/en/open-government-licence-canada',
    url: 'https://www.canada.ca/en/health-canada/services/food-nutrition/healthy-eating/nutrient-data.html',
  },
  {
    source: 'openfoodfacts',
    citation: 'Packaged products from Open Food Facts, a free and open database of food products.',
    licence: 'Open Database Licence (ODbL)',
    licenceUrl: 'https://opendatacommons.org/licenses/odbl/1-0/',
    url: 'https://world.openfoodfacts.org/',
  },
]
