import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useDictation } from '../hooks/useDictation'
import type { Confidence, MealAnalysisResponse, Settings } from '../types'

interface Props {
  settings: Settings | null
  onApply: (analysis: MealAnalysisResponse) => void
}

const confidenceBadge: Record<Confidence, string> = {
  high: 'bg-emerald-500/15 text-emerald-300',
  medium: 'bg-amber-500/15 text-amber-300',
  low: 'bg-rose-500/15 text-rose-300',
}

const confidenceDots: Record<Confidence, string> = {
  high: '●●●',
  medium: '●●○',
  low: '●○○',
}

const round = (value: number) => Math.round(value)

export default function MealAnalyzer({ settings, onApply }: Props) {
  const [expanded, setExpanded] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [note, setNote] = useState('')
  const [analysis, setAnalysis] = useState<MealAnalysisResponse | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const noteRef = useRef<HTMLTextAreaElement>(null)

  const dictation = useDictation((transcript) => {
    setNote((current) => (current ? `${current} ${transcript}` : transcript))
  })

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  const analyze = async (refine: boolean) => {
    if (!file && !note.trim()) {
      setError('Add a photo or describe the meal first.')
      return
    }
    setAnalyzing(true)
    setError(null)
    try {
      const form = new FormData()
      if (file) form.append('image', file)
      if (note.trim()) form.append('text', note.trim())
      if (refine && analysis) form.append('prior_analysis', JSON.stringify(analysis))
      setAnalysis(await api.analyzeMeal(form))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Analysis failed')
    } finally {
      setAnalyzing(false)
    }
  }

  const correctAssumption = (assumption: string) => {
    setNote((current) => {
      const prefix = current.trim() ? `${current.trim()}\n` : ''
      return `${prefix}Correction: ${assumption} → `
    })
    noteRef.current?.focus()
  }

  const inputClass =
    'w-full rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-sm placeholder-slate-500 focus:border-emerald-500 focus:outline-none'

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="w-full rounded-xl border border-dashed border-slate-700 py-3 text-sm text-slate-400 hover:border-emerald-500 hover:text-emerald-300"
      >
        📷 Analyze a meal with AI — photo, description, or both
      </button>
    )
  }

  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="font-semibold">AI meal analysis</h3>
        <button
          onClick={() => setExpanded(false)}
          className="text-xs text-slate-500 hover:text-slate-300"
        >
          Hide
        </button>
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block text-xs text-slate-400">Meal photo (optional)</span>
          <input
            type="file"
            accept="image/*"
            capture="environment"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="block w-full text-xs text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-xs file:text-slate-200 hover:file:bg-slate-700"
          />
          {previewUrl && (
            <img
              src={previewUrl}
              alt="Meal preview"
              className="mt-2 max-h-40 rounded-lg border border-slate-800 object-cover"
            />
          )}
        </label>

        <label className="block text-sm">
          <span className="mb-1 flex items-center justify-between text-xs text-slate-400">
            Describe it (optional)
            {dictation.supported && (
              <button
                type="button"
                onClick={dictation.toggle}
                title={dictation.listening ? 'Stop dictation' : 'Dictate'}
                className={`rounded px-1.5 py-0.5 text-sm ${
                  dictation.listening
                    ? 'animate-pulse bg-rose-500/20 text-rose-300'
                    : 'hover:bg-slate-800'
                }`}
              >
                🎤
              </button>
            )}
          </span>
          <textarea
            ref={noteRef}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={4}
            placeholder={'e.g. "Grilled chicken with ~1 tbsp olive oil, I only ate half the rice"'}
            className={inputClass}
          />
        </label>
      </div>

      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={() => analyze(false)}
          disabled={analyzing}
          className="rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
        >
          {analyzing ? 'Analyzing…' : analysis ? 'Analyze again' : 'Analyze'}
        </button>
        {analysis && (
          <button
            onClick={() => analyze(true)}
            disabled={analyzing}
            className="rounded-lg border border-slate-700 px-5 py-2 text-sm text-slate-300 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-60"
          >
            Refine with my note
          </button>
        )}
        <p className="text-xs text-slate-500">
          Estimates are approximate — review before saving.
        </p>
      </div>

      {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}

      {analysis && (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-800/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h4 className="font-semibold">{analysis.meal_name}</h4>
            <span
              className={`rounded px-2 py-0.5 text-[10px] font-semibold uppercase ${confidenceBadge[analysis.confidence]}`}
            >
              {analysis.confidence} confidence
            </span>
          </div>

          <p className="mt-2 text-sm">
            <span className="font-semibold text-amber-400">
              ~{round(analysis.calories.estimate)} kcal
            </span>{' '}
            <span className="text-xs text-slate-500">
              ({round(analysis.calories.low)}–{round(analysis.calories.high)})
            </span>
            <span className="mx-2 text-slate-600">·</span>
            <span className="font-semibold text-emerald-400">
              ~{round(analysis.protein.estimate)} g protein
            </span>{' '}
            <span className="text-xs text-slate-500">
              ({round(analysis.protein.low)}–{round(analysis.protein.high)})
            </span>
            {settings?.track_carbs && analysis.carbs && (
              <>
                <span className="mx-2 text-slate-600">·</span>
                <span className="font-semibold text-sky-400">
                  ~{round(analysis.carbs.estimate)} g carbs
                </span>
              </>
            )}
            {settings?.track_fat && analysis.fat && (
              <>
                <span className="mx-2 text-slate-600">·</span>
                <span className="font-semibold text-rose-400">
                  ~{round(analysis.fat.estimate)} g fat
                </span>
              </>
            )}
          </p>

          <p className="mt-2 text-xs text-slate-400">{analysis.explanation}</p>

          {analysis.clarifying_question && (
            <p className="mt-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
              🤔 {analysis.clarifying_question} — answer in the note and hit “Refine”.
            </p>
          )}

          {analysis.assumptions.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs text-slate-500">
                Assumed (tap one to correct it):
              </p>
              <div className="flex flex-wrap gap-1.5">
                {analysis.assumptions.map((assumption) => (
                  <button
                    key={assumption}
                    onClick={() => correctAssumption(assumption)}
                    className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:border-amber-400 hover:text-amber-300"
                  >
                    {assumption} ✎
                  </button>
                ))}
              </div>
            </div>
          )}

          <ul className="mt-3 space-y-1">
            {analysis.items.map((item) => (
              <li
                key={item.name}
                className="flex items-center justify-between text-sm text-slate-300"
              >
                <span>
                  {item.name}{' '}
                  <span className="text-xs text-slate-500">
                    ({round(item.portion_grams)} g)
                  </span>
                </span>
                <span className="text-xs text-slate-400">
                  {round(item.calories)} kcal · {Math.round(item.protein * 10) / 10} g P{' '}
                  <span
                    title={`${item.confidence} confidence`}
                    className={confidenceBadge[item.confidence].split(' ')[1]}
                  >
                    {confidenceDots[item.confidence]}
                  </span>
                </span>
              </li>
            ))}
          </ul>

          <button
            onClick={() => onApply(analysis)}
            className="mt-4 w-full rounded-lg border border-emerald-500/50 bg-emerald-500/10 py-2.5 text-sm font-semibold text-emerald-300 hover:bg-emerald-500/20"
          >
            Use these ingredients ↓ (edit them below before saving)
          </button>
        </div>
      )}
    </section>
  )
}
