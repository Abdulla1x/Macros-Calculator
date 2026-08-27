import {
  DEFAULT_WATER_QUICK_ADDS,
  MAX_WATER_GOAL_ML,
  MAX_WATER_QUICK_ADD_ML,
  MAX_WATER_QUICK_ADDS,
  validateSettingsField,
  validateWaterQuickAdd,
  WATER_ML_PER_KG,
} from '../../lib/limits'
import { num } from '../../lib/parse'
import type { Settings as SettingsType } from '../../types'
import Card from '../ui/Card'
import TextInput from '../ui/TextInput'

/** Water goal and quick-add buttons.
 *
 * The goal is a radio pair rather than a "leave blank to derive it" input,
 * because an empty box does not say what an empty box means. Choosing "from my
 * weight" writes null, which is what the server reads as "derive it".
 */
export default function WaterSection({
  settings,
  update,
  onRejected,
}: {
  settings: SettingsType
  update: (patch: Partial<SettingsType>) => void
  onRejected: (message: string) => void
}) {
  const derived = settings.water_goal_ml === null
  const quickAdds = settings.water_quick_adds ?? DEFAULT_WATER_QUICK_ADDS

  // A blank box drops that button rather than storing a zero, so the inputs can
  // express anywhere from one button up to MAX_WATER_QUICK_ADDS without extra
  // UI. The count comes from the constant rather than from the length of
  // DEFAULT_WATER_QUICK_ADDS, which has three entries and is where the
  // off-by-one came from: the server accepts four and the fourth box was never
  // rendered, so the last slot was unreachable from the only screen that sets
  // it.
  //
  // The list is compacted on every edit, and that is not tidiness. Assigning
  // past the end of a shorter array leaves a *hole* — clear two boxes, type
  // into the third, and you get [300, <empty>, 500]. JSON.stringify writes a
  // hole as `null`, the server refuses null for a float, and the user gets a
  // 422 they cannot act on for a field they cannot see is wrong. `filter`
  // skips holes, which is what makes this the fix rather than a workaround.
  const setQuickAdd = (index: number, raw: string) => {
    const next = [...quickAdds]
    const parsed = num(raw)
    if (parsed === null) next.splice(index, 1)
    else next[index] = parsed
    const dense = next.filter((ml) => Number.isFinite(ml))
    update({ water_quick_adds: dense.length > 0 ? dense : null })
  }

  const guardQuickAdd = (index: number) => () => {
    const problem = validateWaterQuickAdd(quickAdds[index] ?? null)
    if (!problem) return
    onRejected(problem)
    // Undone, not flagged — the same rule the profile fields follow.
    const next = [...quickAdds]
    next.splice(index, 1)
    update({ water_quick_adds: next.length > 0 ? next : null })
  }

  return (
    <Card as="section">
      <h2 className="mb-1 font-semibold">💧 Water</h2>
      <p className="mb-4 text-sm text-slate-400">
        The card on your dashboard. Nothing here is required — leave it alone and
        the goal follows your weight.
      </p>

      <fieldset className="mb-5 space-y-2">
        <legend className="mb-2 text-sm text-slate-400">Daily goal</legend>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            checked={derived}
            onChange={() => update({ water_goal_ml: null })}
            className="mt-1 accent-sky-500"
          />
          <span>
            From my weight
            <span className="mt-0.5 block text-xs text-ink-faint">
              {WATER_ML_PER_KG} ml for every kg of your trend weight. A common
              rule of thumb, not a measurement — and it needs a weigh-in, so
              until then the card shows a general default and says so.
            </span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-sm">
          <input
            type="radio"
            checked={!derived}
            onChange={() => update({ water_goal_ml: 2500 })}
            className="mt-1 accent-sky-500"
          />
          <span className="flex-1">
            Set my own
            {!derived && (
              <span className="mt-1 flex items-center gap-2">
                <TextInput accent="water"
                  type="number"
                  min={1}
                  max={MAX_WATER_GOAL_ML}
                  value={settings.water_goal_ml ?? ''}
                  onChange={(event) =>
                    update({ water_goal_ml: num(event.target.value) })
                  }
                  onBlur={() => {
                    const problem = validateSettingsField(
                      'water_goal_ml',
                      settings.water_goal_ml,
                    )
                    if (!problem) return
                    onRejected(problem)
                    update({ water_goal_ml: 2500 })
                  }}
                  aria-label="Daily water goal in ml"
                  className="w-28"
                />
                <span className="text-xs text-ink-faint">ml</span>
              </span>
            )}
          </span>
        </label>
      </fieldset>

      <div>
        <p className="mb-2 text-sm text-slate-400">Quick-add buttons</p>
        <div className="flex flex-wrap items-center gap-2">
          {Array.from({ length: MAX_WATER_QUICK_ADDS }).map((_, index) => (
            <span key={index} className="flex items-center gap-1">
              <span className="text-xs text-ink-faint">+</span>
              <TextInput accent="water" pad="sm"
                type="number"
                min={1}
                max={MAX_WATER_QUICK_ADD_ML}
                value={quickAdds[index] ?? ''}
                onChange={(event) => setQuickAdd(index, event.target.value)}
                onBlur={guardQuickAdd(index)}
                aria-label={`Quick-add button ${index + 1}, in ml`}
                className="w-20"
              />
            </span>
          ))}
          <span className="text-xs text-ink-faint">
            ml each. Clear one to remove that button.
          </span>
        </div>
      </div>
    </Card>
  )
}
