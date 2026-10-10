import { useEffect, useRef, useState } from 'react'
import { MAX_ATTACHED_FOODS, MAX_IMAGES, useAnalysis } from '../analysis/AnalysisContext'
import type { LibraryContext } from '../lib/libraryMatch'
import { matchItem, perPortion } from '../lib/libraryMatch'
import type { Confidence, MealAnalysisResponse, Settings } from '../types'
import AnalysisProgress from './AnalysisProgress'
import Card from './ui/Card'
import LibraryFoodPicker from './LibraryFoodPicker'
import SaveIngredientToLibrary from './SaveIngredientToLibrary'
import TextInput from './ui/TextInput'
import Button from './ui/Button'
import { useLiveMessage } from '../hooks/useLiveMessage'

interface Props {
  settings: Settings | null
  // The library travels with the analysis because the page below has to resolve
  // the same matches this component displays, and re-fetching there would be a
  // second request for an answer already in memory.
  onApply: (analysis: MealAnalysisResponse, foods: LibraryContext) => void
  /** Always shown, with no Hide: the Log panel puts AI first, so folding it
   *  away behind a button would undo that. */
  alwaysOpen?: boolean
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

/** The AI box on the Log page. Every piece of its state -- the note, the
 *  photos, the call in flight and its answer -- lives in AnalysisProvider, so
 *  leaving the page no longer throws an estimate away; this component only
 *  draws it. */
export default function MealAnalyzer({ settings, onApply, alwaysOpen = false }: Props) {
  const {
    note,
    setNote,
    noteRef,
    files,
    previewUrls,
    addFiles,
    removeFile,
    library,
    loadLibrary,
    attached,
    attach,
    detach,
    savedToLibrary,
    markSaved,
    analysis,
    analyzing,
    transcribing,
    error,
    unchangedRerun,
    dismissUnchangedRerun,
    progress,
    audio,
    analyze,
    correctAssumption,
    watch,
  } = useAnalysis()
  useLiveMessage(error)

  // Open straight away when there is anything to show: a note, photos, an
  // estimate on its way or one already back. Otherwise someone returning to a
  // running estimate would find it folded away behind the button.
  const [expandedByUser, setExpanded] = useState(
    () => note !== '' || files.length > 0 || analyzing || analysis !== null,
  )
  const expanded = alwaysOpen || expandedByUser

  // While this is on screen the provider knows an estimate that lands has been
  // seen, so it neither shows a toast nor puts "Ready" on the Log button.
  useEffect(watch, [watch])

  // Leaving the page stops a recording in progress. The recorder lives in the
  // provider, so without this the mic would stay live on the next page; stopped,
  // what was said is transcribed into the note as usual.
  const { stop: stopRecording } = audio
  useEffect(() => stopRecording, [stopRecording])

  // Fetched when the panel is opened rather than on mount: /log should not pay
  // for a request until the AI is actually in use. Once per mount, so foods
  // saved elsewhere since the last visit show up.
  const libraryRequested = useRef(false)
  useEffect(() => {
    if (!expanded || libraryRequested.current) return
    libraryRequested.current = true
    loadLibrary()
  }, [expanded, loadLibrary])

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        aria-expanded={false}
        className="w-full rounded-xl border border-dashed border-slate-700 py-3 text-sm text-slate-400 hover:border-emerald-500 hover:text-emerald-300"
      >
        <span aria-hidden="true">✨</span> Estimate macros with AI — describe it,
        speak it, or snap a photo
      </button>
    )
  }

  return (
    <Card as="section">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="font-semibold">AI meal analysis</h2>
        {/* The expand control and this one are never on screen together -- each
            branch renders one of them -- so each hard-codes the state it is in,
            the way SaveIngredientToLibrary's does. */}
        {!alwaysOpen && (
          <button
            onClick={() => setExpanded(false)}
            aria-expanded={true}
            className="text-xs text-ink-faint hover:text-slate-300"
          >
            Hide
          </button>
        )}
      </div>

      <p className="mb-3 text-xs text-slate-400">
        A description or a photo is enough — combine them for a sharper estimate.
        The mic writes into the description, so you can fix anything it mishears.
      </p>

      <div className="grid gap-3 sm:grid-cols-2">
        <label className="block text-sm">
          <span className="mb-1 block text-xs text-slate-400">Describe it</span>
          <TextInput as="textarea"
            ref={noteRef}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            rows={4}
            placeholder={'e.g. "Grilled chicken with ~1 tbsp olive oil, I only ate half the rice"'}
            className="w-full"
          />
        </label>

        <div className="block text-sm">
          <label className="block">
            <span className="mb-1 block text-xs text-slate-400">
              Meal photos{' '}
              <span className="text-ink-faint">
                ({files.length}/{MAX_IMAGES} — more angles sharpen the estimate)
              </span>
            </span>
            {/* No `capture` attribute, deliberately. It is not a hint: it tells
                the browser to acquire from a camera and skip the file picker,
                so on Android it made the gallery unreachable. Desktop has no
                capture flow to invoke and ignored it, which is why this looked
                like a phone-only bug for months. `accept` alone gets the OS
                chooser — Camera, Gallery and Files — so taking a photo still
                works. */}
            <input
              type="file"
              accept="image/*"
              multiple
              onChange={(e) => {
                addFiles(e.target.files)
                // Cleared so picking the same file again still fires a change
                // event — otherwise removing a photo and re-adding it silently
                // does nothing.
                e.target.value = ''
              }}
              disabled={files.length >= MAX_IMAGES}
              className="block w-full text-xs text-slate-400 file:mr-3 file:rounded-lg file:border-0 file:bg-slate-800 file:px-3 file:py-2 file:text-xs file:text-slate-200 hover:file:bg-slate-700 disabled:opacity-50"
            />
          </label>
          {previewUrls.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-2">
              {previewUrls.map((url, index) => (
                <li key={url} className="relative">
                  <img
                    src={url}
                    alt={`Meal photo ${index + 1}`}
                    className="h-20 w-20 rounded-lg border border-slate-800 object-cover"
                  />
                  <button
                    type="button"
                    onClick={() => removeFile(index)}
                    aria-label={`Remove photo ${index + 1}`}
                    className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full border border-slate-700 bg-slate-900 text-xs text-slate-300 hover:border-rose-500 hover:text-rose-400"
                  >
                    ✕
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      <LibraryFoodPicker
        foods={library}
        attached={attached}
        max={MAX_ATTACHED_FOODS}
        onAttach={attach}
        onDetach={detach}
      />

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
            <span aria-hidden="true">🎤</span>{' '}
            {audio.recording ? 'Stop recording' : 'Record a voice note'}
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
        <Button
          onClick={() => analyze(false)}
          disabled={analyzing || transcribing}
          className="px-5 py-2"
        >
          {analyzing ? 'Analyzing…' : analysis ? 'Analyze again' : 'Analyze'}
        </Button>
        {analysis && (
          <button
            onClick={() => analyze(true)}
            disabled={analyzing || transcribing}
            className="rounded-lg border border-slate-700 px-5 py-2 text-sm text-slate-300 hover:border-emerald-500 hover:text-emerald-300 disabled:opacity-60"
          >
            Refine with my note
          </button>
        )}
        <p className="text-xs text-ink-faint">
          Estimates are approximate — review before saving.
        </p>
      </div>

      {analysis && (
        <p className="mt-2 text-xs text-ink-faint">
          <span className="text-slate-300">Refine</span> adjusts this estimate to your
          note — use it after correcting an assumption.{' '}
          <span className="text-slate-300">Analyze again</span> starts over — use it
          after adding photos.
        </p>
      )}

      {unchangedRerun && (
        <div
          role="status"
          className="mt-3 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-300"
        >
          <p>
            Nothing has changed since this estimate: same note, photos and saved
            foods. Running it again uses one of today's AI estimates and usually
            moves the numbers only a few percent.
          </p>
          <div className="mt-2 flex gap-3">
            {/* Same rule as the buttons above: a voice note still transcribing
                is about to change the note, so running now would send it without. */}
            <button
              type="button"
              onClick={() => analyze(unchangedRerun === 'refine', true)}
              disabled={analyzing || transcribing}
              className="rounded-lg border border-amber-500/50 px-3 py-1.5 text-amber-200 hover:bg-amber-500/10 disabled:opacity-60"
            >
              Run it anyway
            </button>
            <button
              type="button"
              onClick={dismissUnchangedRerun}
              className="px-1 text-ink-faint hover:text-slate-300"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <p className="mt-2 text-xs text-ink-faint">
        Your photo, voice note, and description are sent to Google Gemini for analysis.
      </p>

      <AnalysisProgress state={progress} />

      {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}

      {analysis && (
        <div className="mt-4 rounded-lg border border-slate-800 bg-slate-800/40 p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h3 className="font-semibold">{analysis.meal_name}</h3>
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
            <span className="text-xs text-ink-faint">
              ({round(analysis.calories.low)}–{round(analysis.calories.high)})
            </span>
            <span className="mx-2 text-ink-faint">·</span>
            <span className="font-semibold text-emerald-400">
              ~{round(analysis.protein.estimate)} g protein
            </span>{' '}
            <span className="text-xs text-ink-faint">
              ({round(analysis.protein.low)}–{round(analysis.protein.high)})
            </span>
            {settings?.track_carbs && analysis.carbs && (
              <>
                <span className="mx-2 text-ink-faint">·</span>
                <span className="font-semibold text-sky-400">
                  ~{round(analysis.carbs.estimate)} g carbs
                </span>
              </>
            )}
            {settings?.track_fat && analysis.fat && (
              <>
                <span className="mx-2 text-ink-faint">·</span>
                <span className="font-semibold text-rose-400">
                  ~{round(analysis.fat.estimate)} g fat
                </span>
              </>
            )}
          </p>

          <p className="mt-2 text-xs text-slate-400">{analysis.explanation}</p>

          {analysis.clarifying_question && (
            <p className="mt-2 rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-300">
              <span aria-hidden="true">🤔</span> {analysis.clarifying_question} — answer in
              the note and hit “Refine”.
            </p>
          )}

          {analysis.assumptions.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-xs text-ink-faint">
                Assumed (tap one to correct it):
              </p>
              <div className="flex flex-wrap gap-1.5">
                {analysis.assumptions.map((assumption) => (
                  <button
                    key={assumption}
                    onClick={() => correctAssumption(assumption)}
                    className="rounded-full border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:border-amber-400 hover:text-amber-300"
                  >
                    {assumption} <span aria-hidden="true">✎</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <ul className="mt-3 space-y-2">
            {analysis.items.map((item) => {
              // Matched against the attached foods only. The rest of the library
              // is deliberately not consulted here: an item nobody attached is
              // the model's own estimate, and quietly rewriting it because a name
              // coincides would be the app deciding on the user's behalf. LogMeal
              // offers that swap per row instead.
              const matched = matchItem(item, attached)
              // The library's figures where there are any, so this list and the
              // rows the apply button produces cannot disagree about one
              // ingredient.
              const macros = matched ? perPortion(item, matched) : item
              return (
                <li key={item.name} className="text-sm text-slate-300">
                  <div className="flex items-center justify-between gap-2">
                    <span>
                      {item.name}{' '}
                      <span className="text-xs text-ink-faint">
                        ({round(item.portion_grams)} g)
                      </span>
                      {matched && (
                        <span className="ml-1.5 rounded bg-emerald-500/15 px-1.5 py-0.5 text-[10px] uppercase text-emerald-300">
                          your library
                        </span>
                      )}
                    </span>
                    <span className="shrink-0 text-xs text-slate-400">
                      {round(macros.calories)} kcal ·{' '}
                      {Math.round(macros.protein * 10) / 10} g P{' '}
                      <span
                        title={`${item.confidence} confidence`}
                        className={confidenceBadge[item.confidence].split(' ')[1]}
                      >
                        {confidenceDots[item.confidence]}
                      </span>
                    </span>
                  </div>
                  {/* Only for items the model estimated. A matched item is a
                      library food already -- it is where these numbers came
                      from -- so offering to save it would be offering to
                      overwrite it with itself. */}
                  {!matched && (
                    <SaveIngredientToLibrary
                      item={item}
                      library={library}
                      savedAs={savedToLibrary[item.name] ?? null}
                      onSaved={(name) => markSaved(item.name, name)}
                    />
                  )}
                </li>
              )
            })}
          </ul>

          {analysis.items.some((item) => matchItem(item, attached)) && (
            <p className="mt-2 text-xs text-ink-faint">
              Macros marked “your library” are your own saved numbers — only the
              portion was estimated. The meal total above is the AI's own, so it
              can differ from these by a little.
            </p>
          )}

          <button
            onClick={() => onApply(analysis, { attached, library })}
            className="mt-4 w-full rounded-lg border border-emerald-500/50 bg-emerald-500/10 py-2.5 text-sm font-semibold text-emerald-300 hover:bg-emerald-500/20"
          >
            {/* In the Log panel the form is the next screen; when editing a
                meal it is right below. */}
            {alwaysOpen
              ? 'Use these ingredients → (check them before saving)'
              : 'Use these ingredients ↓ (edit them below before saving)'}
          </button>
        </div>
      )}
    </Card>
  )
}
