import { useEffect, useRef, useState } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { api } from '../api/client'
import CalibrationSection from '../components/CalibrationSection'
import { localIsoDate } from '../lib/dates'
import { useSettings } from '../settings/SettingsContext'
import type { AnalyticsSummary, ImportResult } from '../types'

/** One average tile, with its sample size when that is not the obvious one.
 *
 *  Zero recorded days renders an em dash rather than "0 g". An average over no
 *  observations is not zero, it is nothing, and printing a number there would
 *  invent data — which is precisely what the per-macro denominator was changed
 *  to stop doing. */
const macroStat = (
  label: string,
  average: number,
  unit: string,
  days: number,
  loggedDays: number,
) => ({
  label,
  value: days === 0 ? '—' : `${Math.round(average)} ${unit}`,
  note:
    days === 0
      ? 'not recorded in this range'
      : days === loggedDays
        ? null
        : `over the ${days} day${days === 1 ? '' : 's'} you recorded it`,
})

const defaultStart = () => {
  const date = new Date()
  date.setDate(date.getDate() - 29)
  return localIsoDate(date)
}

interface MacroChart {
  key: 'calories' | 'protein' | 'carbs' | 'fat'
  label: string
  color: string
  unit: string
}

const macroCharts: MacroChart[] = [
  { key: 'calories', label: 'Calories', color: '#f59e0b', unit: 'kcal' },
  { key: 'protein', label: 'Protein', color: '#34d399', unit: 'g' },
  { key: 'carbs', label: 'Carbs', color: '#38bdf8', unit: 'g' },
  { key: 'fat', label: 'Fat', color: '#fb7185', unit: 'g' },
]

export default function Analytics() {
  const { settings } = useSettings()
  const [start, setStart] = useState(defaultStart)
  const [end, setEnd] = useState(localIsoDate())
  const [summary, setSummary] = useState<AnalyticsSummary | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const [importError, setImportError] = useState('')
  const [importing, setImporting] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)

  async function handleExport() {
    setExportError('')
    setExporting(true)
    try {
      await api.downloadExport()
    } catch (err) {
      setExportError(err instanceof Error ? err.message : 'Export failed')
    } finally {
      setExporting(false)
    }
  }

  useEffect(() => {
    // The stale flag stops an out-of-order response for a previous range from
    // overwriting the current one.
    let stale = false
    setLoadError(null)
    api
      .getAnalytics(start, end)
      .then((result) => {
        if (!stale) setSummary(result)
      })
      .catch((err) => {
        if (stale) return
        setSummary(null)
        setLoadError(err instanceof Error ? err.message : 'Could not load analytics.')
      })
    return () => {
      stale = true
    }
  }, [start, end])

  // Hide optional charts when untracked or when no day in range has data
  // (e.g. meals migrated from v1 have no carbs/fat).
  const hasData = (key: MacroChart['key']) =>
    summary?.days.some((day) => day[key] != null) ?? false

  const visibleCharts = macroCharts.filter(
    (chart) =>
      chart.key === 'calories' ||
      chart.key === 'protein' ||
      (chart.key === 'carbs' && settings?.track_carbs && hasData('carbs')) ||
      (chart.key === 'fat' && settings?.track_fat && hasData('fat')),
  )

  const importFile = async (file: File) => {
    setImporting(true)
    setImportError('')
    setImportResult(null)
    try {
      setImportResult(await api.importCsv(file))
      setSummary(await api.getAnalytics(start, end))
    } catch (error) {
      setImportError(error instanceof Error ? error.message : 'Import failed')
    } finally {
      setImporting(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const inputClass =
    'rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm focus:border-emerald-500 focus:outline-none'

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-2xl font-bold">Analytics</h2>
        <p className="text-sm text-slate-400">Trends and averages over any date range.</p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="block text-sm">
          <span className="mb-1 block text-xs text-slate-400">From</span>
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className={inputClass} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-xs text-slate-400">To</span>
          <input type="date" value={end} onChange={(e) => setEnd(e.target.value)} className={inputClass} />
        </label>
      </div>

      {summary && summary.days.length > 0 ? (
        <>
          <section className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            {[
              { label: 'Days logged', value: String(summary.days.length), note: null },
              macroStat('Avg calories / day', summary.averages.calories, 'kcal', summary.average_days.calories, summary.logged_days),
              macroStat('Avg protein / day', summary.averages.protein, 'g', summary.average_days.protein, summary.logged_days),
              ...(settings?.track_carbs
                ? [macroStat('Avg carbs / day', summary.averages.carbs, 'g', summary.average_days.carbs, summary.logged_days)]
                : []),
              ...(settings?.track_fat
                ? [macroStat('Avg fat / day', summary.averages.fat, 'g', summary.average_days.fat, summary.logged_days)]
                : []),
              { label: 'Total calories', value: Math.round(summary.totals.calories).toLocaleString(), note: null },
            ].map((stat) => (
              <div key={stat.label} className="rounded-xl border border-slate-800 bg-slate-900 p-4">
                <p className="text-xs text-slate-400">{stat.label}</p>
                <p className="mt-1 text-xl font-bold">{stat.value}</p>
                {/* Only when this macro's denominator differs from the number
                    of logged days. Printing "over 12 of 12 days" on every tile
                    would be noise that trains people to stop reading the one
                    time it matters. */}
                {stat.note && <p className="mt-1 text-xs text-slate-400">{stat.note}</p>}
              </div>
            ))}
          </section>

          {/* States the denominator so "Days logged" and "Avg / day" read as
              the pair they are. Widening the range over days you never logged
              no longer moves these numbers, which is the whole point. */}
          <p className="-mt-2 text-xs text-slate-400">
            Averages are per day you logged, not per day in the range — a day
            with nothing recorded is missing data, not a day of zero intake.
            Each macro is averaged over the days it was actually recorded on, so
            tracking carbs or fat only sometimes does not drag their average
            down; where that differs from the days you logged, the tile says so.
          </p>

          {visibleCharts.map((chart) => (
            <section key={chart.key} className="rounded-xl border border-slate-800 bg-slate-900 p-5">
              <h3 className="mb-3 font-semibold" style={{ color: chart.color }}>
                {chart.label} over time
              </h3>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={summary.days} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                  <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    tick={{ fill: '#64748b', fontSize: 11 }}
                    tickFormatter={(value: string) => value.slice(5)}
                    stroke="#334155"
                  />
                  <YAxis tick={{ fill: '#64748b', fontSize: 11 }} stroke="#334155" />
                  <Tooltip
                    contentStyle={{ background: '#1e293b', border: '1px solid #334155', borderRadius: 8 }}
                    labelStyle={{ color: '#e2e8f0' }}
                    formatter={(value) => [`${Math.round(Number(value) * 10) / 10} ${chart.unit}`, chart.label]}
                  />
                  <Line
                    type="monotone"
                    dataKey={chart.key}
                    stroke={chart.color}
                    strokeWidth={2}
                    dot={{ r: 2.5, fill: chart.color }}
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </section>
          ))}

          <section className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 text-left text-xs uppercase text-slate-400">
                  <th className="px-4 py-3">Date</th>
                  <th className="px-4 py-3">Calories</th>
                  <th className="px-4 py-3">Protein (g)</th>
                  {settings?.track_carbs && <th className="px-4 py-3">Carbs (g)</th>}
                  {settings?.track_fat && <th className="px-4 py-3">Fat (g)</th>}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {[...summary.days].reverse().map((day) => (
                  <tr key={day.date} className="hover:bg-slate-800/40">
                    <td className="px-4 py-2.5">{day.date}</td>
                    <td className="px-4 py-2.5">{Math.round(day.calories)}</td>
                    <td className="px-4 py-2.5">{Math.round(day.protein * 10) / 10}</td>
                    {settings?.track_carbs && (
                      <td className="px-4 py-2.5">{day.carbs == null ? '—' : Math.round(day.carbs * 10) / 10}</td>
                    )}
                    {settings?.track_fat && (
                      <td className="px-4 py-2.5">{day.fat == null ? '—' : Math.round(day.fat * 10) / 10}</td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        </>
      ) : loadError ? (
        <p className="rounded-xl border border-rose-900/60 bg-slate-900 p-6 text-center text-sm text-rose-300">
          {loadError}
        </p>
      ) : (
        <p className="rounded-xl border border-slate-800 bg-slate-900 p-6 text-center text-sm text-slate-500">
          No meals in this date range yet.
        </p>
      )}

      <CalibrationSection />

      <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h3 className="mb-3 font-semibold">Backup & restore</h3>
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={handleExport}
            disabled={exporting}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-60"
          >
            {exporting ? 'Exporting…' : '⬇️ Export all meals (CSV)'}
          </button>
          <button
            onClick={() => fileInput.current?.click()}
            disabled={importing}
            className="rounded-lg border border-slate-700 px-4 py-2 text-sm hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-60"
          >
            {importing ? 'Importing…' : '⬆️ Import meals (CSV)'}
          </button>
          <input
            ref={fileInput}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => e.target.files?.[0] && importFile(e.target.files[0])}
          />
        </div>
        {importResult && (
          <p className="mt-3 text-sm text-emerald-400">
            Imported {importResult.inserted} meals — skipped {importResult.skipped_duplicates}{' '}
            duplicates, {importResult.skipped_invalid} invalid rows.
          </p>
        )}
        {importError && <p className="mt-3 text-sm text-rose-400">{importError}</p>}
        {exportError && <p className="mt-3 text-sm text-rose-400">{exportError}</p>}
        <p className="mt-2 text-xs text-slate-500">
          CSV columns: date, name, calories, protein (carbs and fat optional).
        </p>
      </section>
    </div>
  )
}
