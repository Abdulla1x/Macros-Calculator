import { fieldClass } from './fieldClass'
import { num } from '../../lib/parse'
import { cmToFtIn, ftInToCm } from '../../lib/units'
import type { Settings as SettingsType } from '../../types'

/** Height, in whichever unit the weight preference implies.
 *
 * The API is always centimetres; feet and inches exist only here and in
 * lib/units.ts. The round trip is stable — cmToFtIn rounds to the nearest inch
 * and ftInToCm to the nearest millimetre — so this can derive the displayed
 * feet/inches from the stored cm each render instead of holding a second copy
 * of the value that could drift out of step with it. */
export default function HeightField({
  settings,
  update,
  onBlur,
}: {
  settings: SettingsType
  update: (patch: Partial<SettingsType>) => void
  onBlur: () => void
}) {
  if (settings.weight_unit !== 'lb') {
    return (
      <label className="block text-sm">
        <span className="mb-1 block text-slate-400">Height (cm)</span>
        <input
          type="number"
          value={settings.height_cm ?? ''}
          onChange={(event) => update({ height_cm: num(event.target.value) })}
          onBlur={onBlur}
          className={fieldClass}
        />
      </label>
    )
  }

  const { feet, inches } = settings.height_cm
    ? cmToFtIn(settings.height_cm)
    : { feet: 0, inches: 0 }
  const set = (nextFeet: number | null, nextInches: number | null) => {
    // Both boxes empty means "not set", not "zero tall".
    if (nextFeet === null && nextInches === null) {
      update({ height_cm: null })
      return
    }
    update({ height_cm: ftInToCm(nextFeet ?? 0, nextInches ?? 0) })
  }

  return (
    <div className="text-sm">
      <span className="mb-1 block text-slate-400">Height</span>
      <div className="flex gap-2">
        <label className="flex-1">
          <input
            type="number"
            aria-label="Height, feet"
            placeholder="ft"
            value={settings.height_cm ? feet : ''}
            onChange={(event) =>
              set(num(event.target.value), settings.height_cm ? inches : null)
            }
            onBlur={onBlur}
            className={fieldClass}
          />
        </label>
        <label className="flex-1">
          <input
            type="number"
            aria-label="Height, inches"
            placeholder="in"
            value={settings.height_cm ? inches : ''}
            onChange={(event) =>
              set(settings.height_cm ? feet : null, num(event.target.value))
            }
            onBlur={onBlur}
            className={fieldClass}
          />
        </label>
      </div>
      <span className="mt-1 block text-xs text-ink-faint">
        Stored in centimetres; shown in feet and inches because your weight unit
        is pounds.
      </span>
    </div>
  )
}
