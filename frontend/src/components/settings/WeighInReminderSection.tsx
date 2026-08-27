import { MAX_WEIGH_IN_REMINDER_DAYS } from '../../lib/limits'
import { num } from '../../lib/parse'
import type { Settings as SettingsType } from '../../types'
import Card from '../ui/Card'
import Field from '../ui/Field'
import TextInput from '../ui/TextInput'

/** The weigh-in reminder: whether, when, and how often.
 *
 * On the Body tab rather than beside the three trackers, because this is a
 * setting about the Weight page and Units — directly above it — already is one.
 *
 * Two controls for two columns. The time carries the opt-in (empty is off), so
 * there is no separate toggle to disagree with it. The frequency is never
 * empty, which is what stops it becoming a second way to spell "off".
 *
 * The frequency box stays visible and enabled while the reminder is off rather
 * than being hidden or disabled. Hiding it would jump the layout on the first
 * keystroke into the time field, and disabling it would stop someone setting up
 * the cadence and the time in whichever order they think of them.
 */
export default function WeighInReminderSection({
  settings,
  update,
  onBlur,
}: {
  settings: SettingsType
  update: (patch: Partial<SettingsType>) => void
  onBlur: () => void
}) {
  const on = settings.weigh_in_reminder_time !== null

  return (
    <Card as="section">
      <h2 className="mb-1 font-semibold">⚖️ Weigh-in reminder</h2>
      <p className="mb-4 text-sm text-slate-400">
        Your weigh-ins are not just a chart — they are what the trend line, your
        measured daily burn and (if you have them switched on) your automatic
        targets are all worked out from. Skipped days make every one of those
        thinner. Set a time and this will say so.{' '}
        <strong className="text-slate-300">
          It only speaks while the app is open on this device, and nothing here
          will notify your phone
        </strong>
        . Push notifications on Android go through Google Play Services and
        scheduled local ones need a browser feature that was never built — the
        same wall the supplement reminders hit. Leave the time empty and none of
        this happens.
      </p>

      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Remind me at"
          caption="Leave empty to switch the reminder off."
        >
          <TextInput
            type="time"
            value={settings.weigh_in_reminder_time ?? ''}
            onChange={(event) =>
              update({ weigh_in_reminder_time: event.target.value || null })
            }
            className="w-full"
          />
        </Field>

        <Field
          label="After this many days without a weigh-in"
          caption={
            on
              ? '1 means any day you have not weighed in yet.'
              : 'Kept for when you switch the reminder back on.'
          }
        >
          <span className="flex items-center gap-2">
            <TextInput
              type="number"
              min={1}
              max={MAX_WEIGH_IN_REMINDER_DAYS}
              value={settings.weigh_in_reminder_days}
              onChange={(event) =>
                // Falls back to 1 rather than null: the column is NOT NULL, and
                // an empty box mid-edit must not send a value the server will
                // refuse. The guard on blur catches anything out of range.
                update({ weigh_in_reminder_days: num(event.target.value) ?? 1 })
              }
              onBlur={onBlur}
              aria-label="Days without a weigh-in before reminding me"
              className="w-24"
            />
            <span className="text-xs text-ink-faint">days</span>
          </span>
        </Field>
      </div>
    </Card>
  )
}
