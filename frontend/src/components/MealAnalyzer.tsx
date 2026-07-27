import { useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import { useAudioRecorder, voiceNoteFilename } from '../hooks/useAudioRecorder'
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
  const [transcribing, setTranscribing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const noteRef = useRef<HTMLTextAreaElement>(null)

  const audio = useAudioRecorder()
  const { blob: recording, durationMs, clear: clearRecording } = audio

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      return
    }
    const url = URL.createObjectURL(file)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  // Transcribe the moment a recording lands, rather than sending the audio
  // along with the analysis: the text drops into the box below where it can be
  // corrected first, so a misheard ingredient is a typo to fix instead of a
  // wrong number to notice afterwards.
  useEffect(() => {
    if (!recording) return

    // An accidental tap on the mic produces a fraction of a second of silence,
    // and the model will confidently transcribe that as a stray word rather
    // than nothing. Cheaper to catch here than to send it and let the user
    // wonder where "one" came from.
    if (durationMs < 500) {
      setError('That recording was too short — hold the button while you speak.')
      clearRecording()
      return
    }

    let cancelled = false

    const transcribe = async () => {
      setTranscribing(true)
      setError(null)
      try {
        const form = new FormData()
        form.append('audio', recording, voiceNoteFilename(recording.type))
        const { transcript } = await api.transcribeVoiceNote(form)
        if (cancelled) return
        setNote((current) =>
          current.trim() ? `${current.trim()} ${transcript}` : transcript,
        )
        noteRef.current?.focus()
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Could not transcribe that')
        }
      } finally {
        if (!cancelled) {
          setTranscribing(false)
          // Either way the recording is spent — dropping it lets the user just
          // record again instead of having to discard a failed one first.
          clearRecording()
        }
      }
    }

    void transcribe()
    return () => {
      cancelled = true
    }
  }, [recording, durationMs, clearRecording])

  const analyze = async (refine: boolean) => {
    if (!file && !note.trim()) {
      setError('Describe the meal, record a voice note, or add a photo first.')
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
        ✨ Estimate macros with AI — describe it, speak it, or snap a photo
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

      <p className="mb-3 text-xs text-slate-400">
        A description or a photo is enough — combine them for a sharper estimate.
        The mic writes into the description, so you can fix anything it mishears.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block text-xs text-slate-400">Describe it</span>
          <textarea
            ref={noteRef}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={4}
            placeholder={'e.g. "Grilled chicken with ~1 tbsp olive oil, I only ate half the rice"'}
            className={inputClass}
          />
        </label>

        <label className="block text-sm">
          <span className="mb-1 block text-xs text-slate-400">Meal photo</span>
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
      </div>

      {audio.supported && (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <button
            type="button"
            onClick={audio.toggle}
            disabled={transcribing}
            className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm disabled:opacity-60 ${
              audio.recording
                ? 'animate-pulse border-rose-500/50 bg-rose-500/10 text-rose-300'
                : 'border-slate-700 text-slate-300 hover:border-emerald-500 hover:text-emerald-300'
            }`}
          >
            🎤 {audio.recording ? 'Stop recording' : 'Record a voice note'}
          </button>
          {transcribing && (
            <span className="text-xs text-slate-400">
              Transcribing — the text will appear above, ready to edit…
            </span>
          )}
          {audio.error && <span className="text-xs text-rose-400">{audio.error}</span>}
        </div>
      )}

      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={() => analyze(false)}
          disabled={analyzing || transcribing}
          className="rounded-lg bg-emerald-500 px-5 py-2 text-sm font-semibold text-slate-950 hover:bg-emerald-400 disabled:opacity-60"
        >
          {analyzing ? 'Analyzing…' : analysis ? 'Analyze again' : 'Analyze'}
        </button>
        {analysis && (
          <button
            onClick={() => analyze(true)}
            disabled={analyzing || transcribing}
            className="rounded-lg border border-slate-700 px-5 py-2 text-sm text-slate-300 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-60"
          >
            Refine with my note
          </button>
        )}
        <p className="text-xs text-slate-500">
          Estimates are approximate — review before saving.
        </p>
      </div>

      <p className="mt-2 text-xs text-slate-500">
        Your photo, voice note, and description are sent to Google Gemini for analysis.
      </p>

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
