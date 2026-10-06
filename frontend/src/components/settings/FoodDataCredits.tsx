import { DATA_CREDITS, SOURCE_NAME } from '../../lib/foodSources'
import Card from '../ui/Card'

/** Credits for the food tables and Open Food Facts.
 *
 * Every licence behind the generic-food search except USDA's requires
 * attribution, so this is not decoration: it is the condition the data is
 * used on. Collapsed by default because nobody needs it while logging, but it
 * is one tap away on the page that lists the foods it applies to.
 * backend/app/data/reference/NOTICE.md holds the same credits plus what was
 * changed in each table.
 */
export default function FoodDataCredits() {
  return (
    <Card as="section">
      <details>
        <summary className="cursor-pointer font-semibold">Food data sources</summary>
        <p className="mt-3 text-sm text-slate-400">
          Generic foods in the search come from these open national food tables,
          per 100 g, with carbs shown without fibre. Packaged products come from
          Open Food Facts. None of these organisations endorses this app.
        </p>
        <ul className="mt-3 space-y-3 text-sm">
          {DATA_CREDITS.map((credit) => (
            <li key={credit.source}>
              <a
                href={credit.url}
                target="_blank"
                rel="noreferrer"
                className="font-medium text-slate-200 underline-offset-2 hover:underline"
              >
                {SOURCE_NAME[credit.source]}
              </a>
              <p className="text-slate-400">{credit.citation}</p>
              <a
                href={credit.licenceUrl}
                target="_blank"
                rel="noreferrer"
                className="text-xs text-slate-400 underline underline-offset-2 hover:text-slate-200"
              >
                {credit.licence}
              </a>
            </li>
          ))}
        </ul>
      </details>
    </Card>
  )
}
