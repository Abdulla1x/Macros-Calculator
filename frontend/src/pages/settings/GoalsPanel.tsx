import { useSearchParams } from 'react-router-dom'
import BodyTargetsCard from '../../components/settings/BodyTargetsCard'
import CaloriePlanSection from '../../components/settings/CaloriePlanSection'
import { useSettingsPanel } from './panelContext'
import Card from '../../components/ui/Card'
import TextInput from '../../components/ui/TextInput'
import OptionChip from '../../components/ui/OptionChip'
import Field from '../../components/ui/Field'

interface GoalField {
  key: 'calorie_goal' | 'protein_goal' | 'carbs_goal' | 'fat_goal'
  label: string
  unit: string
}

const goalFields: GoalField[] = [
  { key: 'calorie_goal', label: 'Daily calories', unit: 'kcal' },
  { key: 'protein_goal', label: 'Daily protein', unit: 'g' },
  { key: 'carbs_goal', label: 'Daily carbs', unit: 'g' },
  { key: 'fat_goal', label: 'Daily fat', unit: 'g' },
]

/** What you are aiming at, and how to move it around.
 *
 * Tracked macros sits here rather than with the trackers because it decides
 * which of the four goal fields below it exist at all -- the two are one
 * decision made in two steps, and separating them puts a tab switch in the
 * middle of it.
 */
export default function GoalsPanel() {
  const { settings, update, guard, onRejected, targetsKey } = useSettingsPanel()
  // The day the dashboard was showing when the planning link was followed, so
  // the planner opens on it rather than on today. Absent when Settings is
  // reached any other way, which is the ordinary case.
  //
  // A search param rather than router state, which is what carried it before
  // the split. location.state does not survive a reload and cannot be shared or
  // bookmarked, and this app has already shipped one bug from state outliving
  // what it described (a shared-meal notice that stayed on screen over the next
  // meal typed by hand). A param has neither failure mode.
  const planDate = useSearchParams()[0].get('plan') ?? undefined

  const showGoal = (key: GoalField['key']) =>
    key === 'carbs_goal' ? settings.track_carbs : key === 'fat_goal' ? settings.track_fat : true

  return (
    <div className="space-y-6">
      <Card as="section">
        <h2 className="mb-3 font-semibold">Tracked macros</h2>
        <p className="mb-4 text-sm text-slate-400">
          Calories and protein are always tracked. Enable carbs and fat if you want the full
          breakdown — they appear on the dashboard, meal log and analytics.
        </p>
        <div className="flex flex-wrap gap-4">
          {(
            [
              { key: 'track_carbs', label: 'Track carbs' },
              { key: 'track_fat', label: 'Track fat' },
            ] as const
          ).map(({ key, label }) => (
            <OptionChip key={key}>
              <input
                type="checkbox"
                checked={settings[key]}
                onChange={(event) => update({ [key]: event.target.checked })}
                className="h-4 w-4 accent-emerald-500"
              />
              {label}
            </OptionChip>
          ))}
        </div>
      </Card>

      <Card as="section">
        <h2 className="mb-4 font-semibold">Daily goals</h2>

        <OptionChip block className="mb-4">
          <input
            type="checkbox"
            checked={settings.targets_auto}
            onChange={(event) => update({ targets_auto: event.target.checked })}
            className="mt-0.5 h-4 w-4 accent-emerald-500"
          />
          <span>
            Work out my goals from my body profile
            <span className="mt-1 block text-xs text-ink-faint">
              Turning this on <strong>replaces</strong> the four goals below with
              calculated ones, and keeps updating them every time you log a
              weigh-in. Anything you typed here yourself is not kept — hit Save
              to confirm, or untick this to go back to setting them by hand.
            </span>
          </span>
        </OptionChip>

        <div className="grid gap-4 sm:grid-cols-2">
          {goalFields.filter((field) => showGoal(field.key)).map((field) => (
            <Field
              key={field.key}
              label={
                <>
                  {field.label} ({field.unit})
                </>
              }
            >
              <TextInput
                type="number"
                min={1}
                value={settings[field.key]}
                readOnly={settings.targets_auto}
                onChange={(event) => update({ [field.key]: Number(event.target.value) })}
                onBlur={guard(field.key)}
                className={`w-full ${
                  settings.targets_auto ? 'cursor-not-allowed text-slate-400' : ''
                }`}
              />
            </Field>
          ))}
        </div>
        {settings.targets_auto && (
          <p className="mt-3 text-xs text-ink-faint">
            Calculated from your body profile. These update on save and whenever
            you log a weigh-in.
          </p>
        )}
      </Card>

      <BodyTargetsCard reloadKey={targetsKey} unit={settings.weight_unit} />

      <CaloriePlanSection onRejected={onRejected} initialDate={planDate} />
    </div>
  )
}
