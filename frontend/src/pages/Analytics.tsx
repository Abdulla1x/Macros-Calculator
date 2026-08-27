import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
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
import {
  axisStroke,
  axisTick,
  gridStroke,
  macroHues,
  shortDate,
  tooltipLabelStyle,
  tooltipStyle,
} from '../lib/chartTheme'
import { localIsoDate } from '../lib/dates'
import { useSettings } from '../settings/SettingsContext'
import type { AnalyticsSummary, ImportResult } from '../types'
import Card from '../components/ui/Card'
import TextInput from '../components/ui/TextInput'

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
  { key: 'calories', label: 'Calories', color: macroHues.calories, unit: 'kcal' },
  { key: 'protein', label: 'Protein', color: macroHues.protein, unit: 'g' },
  { key: 'carbs', label: 'Carbs', color: macroHues.carbs, unit: 'g' },
  { key: 'fat', label: 'Fat', color: macroHues.fat, unit: 'g' },
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


  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-bold">Analytics</h1>
        <p className="text-sm text-slate-400">Trends and averages over any date range.</p>
      </header>

      <div className="flex flex-wrap items-end gap-3">
        <label className="block text-sm">
          <span className="mb-1 block text-xs text-slate-400">From</span>
          <TextInput type="date" value={start} onChange={(e) => setStart(e.target.value)} />
        </label>
        <label className="block text-sm">
          <span className="mb-1 block text-xs text-slate-400">To</span>
          <TextInput type="date" value={end} onChange={(e) => setEnd(e.target.value)} />
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
              <Card pad="sm" key={stat.label}>
                <p className="text-xs text-slate-400">{stat.label}</p>
                <p className="mt-1 text-xl font-bold">{stat.value}</p>
                {/* Only when this macro's denominator differs from the number
                    of logged days. Printing "over 12 of 12 days" on every tile
                    would be noise that trains people to stop reading the one
                    time it matters. */}
                {stat.note && <p className="mt-1 text-xs text-slate-400">{stat.note}</p>}
              </Card>
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
            <Card as="section" key={chart.key}>
              <h2 className="mb-3 font-semibold" style={{ color: chart.color }}>
                {chart.label} over time
              </h2>
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={summary.days} margin={{ top: 5, right: 10, bottom: 0, left: -10 }}>
                  <CartesianGrid stroke={gridStroke} strokeDasharray="3 3" />
                  <XAxis
                    dataKey="date"
                    tick={axisTick}
                    tickFormatter={shortDate}
                    stroke={axisStroke}
                  />
                  <YAxis tick={axisTick} stroke={axisStroke} />
                  <Tooltip
                    contentStyle={tooltipStyle}
                    labelStyle={tooltipLabelStyle}
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
            </Card>
          ))}

          <Card as="section" pad="none" className="overflow-x-auto">
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
          </Card>
        </>
      ) : loadError ? (
        <Card as="p" tone="danger" pad="lg" className="text-center text-sm text-rose-300">
          {loadError}
        </Card>
      ) : (
        <Card as="p" pad="lg" className="text-center text-sm text-ink-faint">
          No meals in this date range yet.
        </Card>
      )}

      {/* Above the calibration section rather than below it: the review quotes
          one line of that section, so meeting it first makes the longer version
          read as the detail behind a sentence already seen. */}
      <Card as="section">
        <h2 className="font-semibold">Weekly review</h2>
        <p className="mt-2 text-sm text-ink-muted">
          The same figures read as a week: how much you logged, how your intake
          and protein compared with your targets, and whether your weight is
          moving the way you asked it to.{' '}
          <Link to="/review" className="underline hover:text-emerald-300">
            Open the weekly review
          </Link>
          .
        </p>
      </Card>

      <CalibrationSection />

      <Card as="section">
        <h2 className="mb-3 font-semibold">Backup & restore</h2>
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
        <p className="mt-2 text-xs text-ink-faint">
          CSV columns: date, name, calories, protein (carbs and fat optional).
        </p>
      </Card>
    </div>
  )
}
