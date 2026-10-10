import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import { m } from 'motion/react'
import { useAnalysis } from '../../analysis/AnalysisContext'
import { localIsoDate } from '../../lib/dates'
import { matchItem } from '../../lib/libraryMatch'
import { announceMealsChanged } from '../../lib/mealEvents'
import { mealTotals, rowFromAnalyzedItem } from '../../lib/mealRows'
import { saveMeal, saveTemplate } from '../../lib/saveMeal'
import { DURATION, EASE } from '../../lib/motion'
import { useSettings } from '../../settings/SettingsContext'
import type { Confidence, MealAnalysisResponse } from '../../types'
import { Button } from '@/ui/button'
import { Chip } from '@/ui/chip'
import { FIELD } from '@/ui/field'
import { KeepIcon, NextIcon, SavedFoodsIcon } from '@/ui/icons'
import { useToast } from '@/ui/toast'
import SaveIngredientToLibrary from '../SaveIngredientToLibrary'
import { logDate } from './logPanelUrl'
import { useLogPanel } from './useLogPanel'

const CONFIDENCE: Record<Confidence, string> = {
  high: 'fairly sure',
  medium: 'a fair guess',
  low: 'a rough guess',
}

const ROW =
  'flex min-h-[52px] w-full items-center gap-3 py-2 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action'

const round = (value: number) => Math.round(value)

/** An AI estimate, ready to save (DESIGN.md: AI estimate -> Result).
 *
 *  `save` mode is the Log panel: the result ends in "Save meal · N kcal", so an
 *  estimate that is right is saved without opening the form (owner,
 *  2026-10-10). "Check and edit first", or tapping any line, opens the by-hand
 *  form filled in, exactly as "Use these ingredients" did.
 *
 *  `apply` mode is the by-hand form while editing a meal, where the form is
 *  right below: the result only fills it.
 *
 *  Every number shown is what will be saved: each item becomes a form row
 *  (lib/mealRows.ts), so a saved food's own macros replace the model's guess
 *  for that item, and the total is those rows summed, not the model's own
 *  total. Only the likely range is the model's. */
export default function EstimateResult({
  analysis,
  mode,
  onApply,
}: {
  analysis: MealAnalysisResponse
  mode: 'save' | 'apply'
  onApply: () => void
}) {
  const { attached, library, savedToLibrary, markSaved, correctAssumption, reset } = useAnalysis()
  const { settings } = useSettings()
  const { search } = useLocation()
  const { close } = useLogPanel()
  const toast = useToast()
  const [name, setName] = useState(analysis.meal_name)
  const [saving, setSaving] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [kept, setKept] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // Brought into view when a new estimate arrives (and when the panel opens
  // on one, from the toast's View): the inputs sit above it, so on a phone the
  // answer would otherwise land below the fold, behind the very scroll the
  // user did not know to make. Instant under reduced motion.
  const top = useRef<HTMLElement>(null)
  useEffect(() => {
    const still = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    top.current?.scrollIntoView({ block: 'start', behavior: still ? 'auto' : 'smooth' })
  }, [analysis.analysis_id])

  const rows = analysis.items.map((item) => rowFromAnalyzedItem(item, attached))
  const totals = mealTotals(rows)
  // Items the model estimated, as opposed to the user's own saved foods: the
  // ones it makes sense to offer for the library.
  const fresh = analysis.items.filter((item) => !matchItem(item, attached) && item.portion_grams > 0)
  const unsaved = fresh.filter((item) => savedToLibrary[item.name] === undefined)

  const save = async () => {
    if (!name.trim()) {
      setError('Give the meal a name first.')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const meal = await saveMeal({
        rows,
        name,
        date: logDate(search) ?? localIsoDate(),
        analysisId: analysis.analysis_id,
      })
      // The estimate went into this meal, so it is spent: photos, note and all.
      reset()
      announceMealsChanged()
      toast.show({ text: `Saved "${meal.name}".` })
      close()
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't save. Check your connection, then try again.")
      setSaving(false)
    }
  }

  const keep = async () => {
    if (!name.trim()) {
      setError('Give the meal a name first.')
      return
    }
    setError(null)
    try {
      const result = await saveTemplate(rows, name.trim())
      // Saving over a template throws away its ingredient list, and there is
      // no undo, so say which one happened.
      setKept(result.created ? `Kept as a saved meal.` : `Replaced your saved meal "${name.trim()}".`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Saving the meal failed.')
    }
  }

  const macroLine = [
    `${round(totals.protein)} g protein`,
    settings?.track_carbs && totals.carbs !== null && `${round(totals.carbs)} g carbs`,
    settings?.track_fat && totals.fat !== null && `${round(totals.fat)} g fat`,
  ]
    .filter(Boolean)
    .join(' · ')

  return (
    <section ref={top} aria-label="Estimate" className="grid scroll-mt-4 gap-3">
      <div className="grid gap-1 border-b border-rule pb-3">
        <h3 className="text-field-label text-ink-2">Estimate</h3>
        <p className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <span className="text-field-number tabular-nums">
            {round(totals.calories).toLocaleString()}
            <span className="ml-1 text-small font-semibold text-ink-2">kcal</span>
          </span>
          <span className="text-small text-ink-2 tabular-nums">
            likely {round(analysis.calories.low).toLocaleString()} to {round(analysis.calories.high).toLocaleString()}
          </span>
        </p>
        <p className="text-small text-ink-2 tabular-nums">{macroLine}</p>
      </div>

      {mode === 'save' && (
        <label className="grid gap-1">
          <span className="text-small text-ink-2">Meal name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} className={FIELD} />
        </label>
      )}

      {analysis.clarifying_question && (
        <p className="border-l-2 border-ink pl-3 text-small">
          {analysis.clarifying_question} Answer it in your note, then Refine.
        </p>
      )}

      {/* Rows arrive one after another (DESIGN.md Motion: 300ms, 90ms apart,
          rising 10px); a saved food's tag snaps in. Under reduced motion only
          the fade remains (MotionConfig). Ends on y: 0, never 'none'. */}
      <ol className="divide-y divide-rule border-y border-rule">
        {analysis.items.map((item, index) => {
          const matched = matchItem(item, attached)
          const row = rows[index]!
          const kcal = round(row ? mealTotals([row]).calories : item.calories)
          const detail = matched
            ? `${round(item.portion_grams)} g, your numbers`
            : `${round(item.portion_grams)} g, ${CONFIDENCE[item.confidence]}`
          const content = (
            <>
              <span className="grid min-w-0 flex-1 gap-0.5">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold">{item.name}</span>
                  {matched && (
                    <m.span
                      initial={{ scale: 0.5 }}
                      animate={{ scale: [0.5, 1.12, 1] }}
                      transition={{ delay: index * 0.09 + 0.2, duration: DURATION.base }}
                      className="rounded-tag border-[1.5px] border-fact px-1.5 text-[11.5px] font-bold tracking-[0.04em] text-fact uppercase"
                    >
                      Your food
                    </m.span>
                  )}
                </span>
                <span className="text-small text-ink-2">{detail}</span>
              </span>
              <span className="shrink-0 text-row-number tabular-nums">{kcal.toLocaleString()}</span>
              {mode === 'save' && <NextIcon size={18} aria-hidden className="shrink-0 text-ink-2" />}
            </>
          )
          return (
            <m.li
              // Index in the key: the model can name two items the same.
              key={`${index}-${item.name}`}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.09, duration: 0.3, ease: EASE }}
            >
              {mode === 'save' ? (
                // Tap any line to fix it: the form, filled in.
                <button type="button" onClick={onApply} className={ROW}>
                  {content}
                </button>
              ) : (
                <div className={ROW}>{content}</div>
              )}
            </m.li>
          )
        })}
      </ol>

      {analysis.assumptions.length > 0 && (
        <div className="grid gap-2">
          <p className="text-small text-ink-2">Assumed. Tap one to correct it in your note:</p>
          <div className="flex flex-wrap gap-1.5">
            {analysis.assumptions.map((assumption) => (
              <Chip key={assumption} onClick={() => correctAssumption(assumption)} className="h-auto min-h-9 py-1 whitespace-normal">
                {assumption}
              </Chip>
            ))}
          </div>
        </div>
      )}

      {analysis.explanation && <p className="text-small text-ink-2">{analysis.explanation}</p>}

      {fresh.length > 0 || mode === 'save' ? (
        <div className="divide-y divide-rule border-y border-rule">
          {/* One control for the whole estimate, not one under every item
              (UA-20). It opens the same per-food check as before -- name it,
              see it as per 100 g, be warned before it replaces one of yours --
              because a food in the library fills every future meal that names
              it, and that is worth a look first. */}
          {fresh.length > 0 && (
            <div>
              <button type="button" aria-expanded={reviewing} onClick={() => setReviewing((open) => !open)} className={ROW}>
                <SavedFoodsIcon size={18} aria-hidden className="shrink-0" />
                <span className="flex-1">
                  {unsaved.length === 0
                    ? 'New foods saved to your library'
                    : `Save ${unsaved.length === 1 ? 'the new food' : `${unsaved.length} new foods`} to my library`}
                  <span className="block truncate text-small text-ink-2">{fresh.map((item) => item.name).join(', ')}</span>
                </span>
                <span aria-hidden="true" className="text-ink-2">
                  {reviewing ? '▴' : '▾'}
                </span>
              </button>
              {reviewing && (
                <ul className="grid gap-3 pb-3">
                  {fresh.map((item, index) => (
                    <li key={`${index}-${item.name}`} className="text-small">
                      <span className="font-semibold">{item.name}</span>
                      <SaveIngredientToLibrary
                        item={item}
                        library={library}
                        savedAs={savedToLibrary[item.name] ?? null}
                        onSaved={(savedAs) => markSaved(item.name, savedAs)}
                      />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {mode === 'save' && (
            <button type="button" onClick={keep} className={ROW}>
              <KeepIcon size={18} aria-hidden className="shrink-0" />
              <span className="flex-1">
                Keep as a saved meal
                {kept && <span className="block text-small text-ink-2">{kept}</span>}
              </span>
            </button>
          )}
        </div>
      ) : null}

      {analysis.items.some((item) => matchItem(item, attached)) && (
        <p className="text-small text-ink-2">
          “Your food” lines use your own saved numbers; only the portion was estimated.
        </p>
      )}

      {/* Ink and words, never red (DESIGN.md, the No Red Rule). */}
      {error && (
        <p role="alert" className="border-l-2 border-ink pl-3 text-small">
          {error}
        </p>
      )}

      {mode === 'save' ? (
        // The panel's footer: always in reach at the bottom of the sheet, so
        // saving never needs a scroll past a long list of items.
        <div className="sticky bottom-0 -mx-4 flex gap-2 border-t border-rule bg-ground px-4 py-3 desk:-mx-7 desk:px-7">
          <Button variant="secondary" onClick={onApply}>
            Check and edit first
          </Button>
          <Button onClick={save} disabled={saving} className="flex-1">
            {saving ? 'Saving…' : `Save meal · ${round(totals.calories).toLocaleString()} kcal`}
          </Button>
        </div>
      ) : (
        <Button onClick={onApply}>Use these ingredients ↓ (edit them below before saving)</Button>
      )}
    </section>
  )
}

