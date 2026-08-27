import HeightField from '../../components/settings/HeightField'
import { num } from '../../lib/parse'
import type { ActivityLevel, Sex } from '../../types'
import { useSettingsPanel } from './panelContext'
import Card from '../../components/ui/Card'
import TextInput from '../../components/ui/TextInput'
import OptionChip from '../../components/ui/OptionChip'
import Field from '../../components/ui/Field'

const sexOptions: { value: Sex; label: string }[] = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
]

const activityOptions: { value: ActivityLevel; label: string }[] = [
  { value: 'sedentary', label: 'Sedentary — desk job, little exercise' },
  { value: 'light', label: 'Light — exercise 1–3 days a week' },
  { value: 'moderate', label: 'Moderate — exercise 3–5 days a week' },
  { value: 'active', label: 'Active — hard exercise 6–7 days a week' },
  { value: 'very_active', label: 'Very active — physical job, or twice a day' },
]

/** Who the calculations are about.
 *
 * Units shares this panel with the profile rather than sitting with the goals,
 * because it decides how the field directly above it is asked for: HeightField
 * renders centimetres or a feet/inches pair depending on the weight unit. Two
 * tabs apart, changing one silently reshapes the other.
 */
export default function BodyPanel() {
  const { settings, update, guard } = useSettingsPanel()

  return (
    <div className="space-y-6">
      <Card as="section">
        <h2 className="mb-1 font-semibold">Body profile</h2>
        <p className="mb-4 text-sm text-slate-400">
          Optional, and the app works fine without it. Fill it in and we can work
          out your BMI, roughly what you burn in a day, and daily targets that
          follow your weight instead of staying where you first set them.
        </p>
        <div className="grid gap-4 sm:grid-cols-2">
          <HeightField settings={settings} update={update} onBlur={guard('height_cm')} />

          <Field label="Date of birth" caption="Stored as the date, so your age stays right without you editing it.">
            <TextInput
              type="date"
              value={settings.birth_date ?? ''}
              onChange={(event) => update({ birth_date: event.target.value || null })}
              className="w-full"
            />
          </Field>

          <Field className="sm:col-span-2" label="Activity level">
            <TextInput as="select"
              value={settings.activity_level ?? ''}
              onChange={(event) =>
                update({
                  activity_level: (event.target.value || null) as ActivityLevel | null,
                })
              }
              className="w-full"
            >
              <option value="">Not set</option>
              {activityOptions.map(({ value, label }) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </TextInput>
          </Field>

          <div className="text-sm sm:col-span-2">
            <span className="mb-2 block text-slate-400">Sex</span>
            <div className="flex flex-wrap gap-3">
              {sexOptions.map(({ value, label }) => (
                <OptionChip key={value}>
                  <input
                    type="radio"
                    name="sex"
                    checked={settings.sex === value}
                    onChange={() => update({ sex: value })}
                    className="h-4 w-4 accent-emerald-500"
                  />
                  {label}
                </OptionChip>
              ))}
              {settings.sex !== null && (
                <button
                  type="button"
                  onClick={() => update({ sex: null })}
                  className="text-sm text-slate-400 hover:text-slate-200"
                >
                  Clear
                </button>
              )}
            </div>
            <p className="mt-2 text-xs text-ink-faint">
              The formula we use to estimate what you burn (Mifflin-St Jeor) only
              takes male or female. That is a limit of the formula, not of you —
              the field is optional, and everything else here still works without
              it.
            </p>
          </div>

          <Field className="sm:col-span-2" label="Goal rate (kg per week)"
            caption={
              <>
              Negative to lose, positive to gain, 0 to maintain. Leave it blank
              and we won't guess — "not set" and "maintain" aren't the same
              answer. Anything past 1 kg/week gets capped, and we'll say so.
              </>
            }
          >
            <TextInput
              type="number"
              step={0.05}
              value={settings.goal_rate_kg_per_week ?? ''}
              onChange={(event) =>
                update({ goal_rate_kg_per_week: num(event.target.value) })
              }
              onBlur={guard('goal_rate_kg_per_week')}
              className="w-full"
            />
          </Field>
        </div>
      </Card>

      <Card as="section">
        <h2 className="mb-3 font-semibold">Units</h2>
        <p className="mb-4 text-sm text-slate-400">
          How weights are shown on the Weight page. Entries are stored the same way
          either way, so switching converts your history rather than rewriting it.
        </p>
        <div className="flex flex-wrap gap-4">
          {(
            [
              { value: 'kg', label: 'Kilograms (kg)' },
              { value: 'lb', label: 'Pounds (lb)' },
            ] as const
          ).map(({ value, label }) => (
            <OptionChip key={value}>
              <input
                type="radio"
                name="weight_unit"
                value={value}
                checked={settings.weight_unit === value}
                onChange={() => update({ weight_unit: value })}
                className="h-4 w-4 accent-emerald-500"
              />
              {label}
            </OptionChip>
          ))}
        </div>
      </Card>
    </div>
  )
}
