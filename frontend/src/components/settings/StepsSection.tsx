import { useRef, useState } from 'react'
import { api } from '../../api/client'
import { MAX_STEPS_PER_DAY, validateSettingsField } from '../../lib/limits'
import { num } from '../../lib/parse'
import type { ImportResult, Settings as SettingsType } from '../../types'
import Card from '../ui/Card'
import TextInput from '../ui/TextInput'
import Field from '../ui/Field'

/** The step goal, and the one place the app admits there is no sync.
 *
 * A single optional input rather than water's radio pair, because the states
 * differ: water is always going to show *a* goal, so the choice is only where
 * it comes from. Steps has no derivation at all, so the choice is whether a
 * goal exists — and an empty box says that perfectly well.
 */
export default function StepsSection({
  settings,
  update,
  onRejected,
}: {
  settings: SettingsType
  update: (patch: Partial<SettingsType>) => void
  onRejected: (message: string) => void
}) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importError, setImportError] = useState('')

  const importFile = async (file: File) => {
    setImporting(true)
    setImportError('')
    setImportResult(null)
    try {
      setImportResult(await api.importStepsCsv(file))
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'Import failed')
    } finally {
      setImporting(false)
      // Cleared so picking the same file again re-fires onChange.
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  return (
    <Card as="section">
      <h2 className="mb-1 font-semibold">👟 Steps</h2>
      <p className="mb-4 text-sm text-slate-400">
        Step counts are typed in by hand. Reading them from your phone or watch
        needs Health Connect or Apple Health, and neither is open to a web app
        like this one — so nothing here syncs, and it is better to say that than
        to leave you waiting for numbers that will never arrive.
      </p>

      <Field label="Daily goal">
        <span className="flex items-center gap-2">
          <TextInput accent="steps"
            type="number"
            min={1}
            max={MAX_STEPS_PER_DAY}
            value={settings.steps_goal ?? ''}
            onChange={(event) => update({ steps_goal: num(event.target.value) })}
            onBlur={() => {
              const problem = validateSettingsField(
                'steps_goal',
                settings.steps_goal,
              )
              if (!problem) return
              onRejected(problem)
              // Undone back to no goal, not to an invented one — the same
              // rule the profile fields follow, and here "unset" is a legal
              // state to land in.
              update({ steps_goal: null })
            }}
            aria-label="Daily step goal"
            className="w-28"
          />
          <span className="text-xs text-ink-faint">steps</span>
        </span>
      </Field>
      <p className="mt-2 text-xs text-ink-faint">
        Leave this empty and the card just shows your count. There is no default
        here on purpose: 10,000 is a slogan from a 1960s pedometer advert, not a
        number worked out from anything about you.
      </p>

      {/* The import sits here rather than beside the meals CSV import on
          Analytics, which costs a little consistency. It buys the thing that
          matters more: it is directly under the sentence saying entry is
          manual, which is exactly where someone thinks "can I not just upload
          this?" */}
      <div className="mt-5 border-t border-slate-800 pt-4">
        <h3 className="mb-1 text-sm font-semibold">Import a step history</h3>
        <p className="mb-3 text-xs text-ink-faint">
          A CSV with a <code className="text-slate-400">date</code> column and a{' '}
          <code className="text-slate-400">steps</code> column, one row per day.
          Extra columns are ignored, so Samsung Health's{' '}
          <em>Download personal data</em> export works as it comes. Apple Health,
          Huawei Health and Health Connect each export a different format — a
          huge XML, a JSON archive and a database respectively — so those need
          converting to two columns first. Days you have already logged are kept,
          never overwritten.
        </p>
        <button
          type="button"
          onClick={() => fileInput.current?.click()}
          disabled={importing}
          className="rounded-lg border border-slate-700 px-3 py-1.5 text-sm text-slate-200 hover:border-violet-500 hover:text-violet-300 disabled:opacity-40"
        >
          {importing ? 'Importing…' : '⬆️ Import steps (CSV)'}
        </button>
        <input
          ref={fileInput}
          type="file"
          accept=".csv,text/csv"
          className="hidden"
          onChange={(event) =>
            event.target.files?.[0] && importFile(event.target.files[0])
          }
        />
        {importResult && (
          <p className="mt-2 text-xs text-slate-400">
            Imported {importResult.inserted} day
            {importResult.inserted === 1 ? '' : 's'} — kept{' '}
            {importResult.skipped_duplicates} already logged,{' '}
            {importResult.skipped_invalid} row
            {importResult.skipped_invalid === 1 ? '' : 's'} could not be read.
          </p>
        )}
        {importError && (
          <p className="mt-2 text-xs text-rose-300">{importError}</p>
        )}
      </div>
    </Card>
  )
}
