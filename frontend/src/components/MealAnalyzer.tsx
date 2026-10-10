import { useEffect, useId, useRef, useState } from 'react'
import { MAX_ATTACHED_FOODS, MAX_IMAGES, useAnalysis } from '../analysis/AnalysisContext'
import type { LibraryContext } from '../lib/libraryMatch'
import { matchItem, perPortion } from '../lib/libraryMatch'
import type { Confidence, MealAnalysisResponse, Settings } from '../types'
import EstimateStages from './log/EstimateStages'
import LibraryFoodPicker from './LibraryFoodPicker'
import SaveIngredientToLibrary from './SaveIngredientToLibrary'
import { Button, buttonVariants } from '@/ui/button'
import { FIELD } from '@/ui/field'
import { CloseIcon, EstimateIcon, PhotoIcon, VoiceIcon } from '@/ui/icons'
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
  const headingId = useId()

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
        className="flex min-h-[52px] w-full items-center gap-3 border-y border-rule text-left text-body focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
      >
        <EstimateIcon size={18} aria-hidden className="text-ink-2" />
        Estimate with AI: describe it, say it or snap it
      </button>
    )
  }

  const busy = analyzing || transcribing
  return (
    <section aria-labelledby={headingId} className="grid gap-3">
      <div className="flex items-center justify-between gap-3">
        <h3 id={headingId} className="text-field-label text-ink-2">
          Estimate with AI
        </h3>
        {/* The expand control and this one are never on screen together -- each
            branch renders one of them -- so each hard-codes the state it is in,
            the way SaveIngredientToLibrary's does. */}
        {!alwaysOpen && (
          <button
            onClick={() => setExpanded(false)}
            aria-expanded={true}
            className="min-h-11 px-1 text-small text-ink-2 underline underline-offset-3 hover:text-ink"
          >
            Hide
          </button>
        )}
      </div>

      <label className="grid gap-1">
        <span className="text-small text-ink-2">Describe it, with weights if you have them</span>
        <textarea
          ref={noteRef}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={4}
          placeholder={'e.g. "150 g chicken, 1 tbsp olive oil, half the rice"'}
          className={`${FIELD} min-h-24 resize-y py-2.5`}
        />
      </label>

      <div className="flex flex-wrap gap-2">
        {/* The mic writes into the description above rather than sending the
            audio with the estimate, so a misheard word is a typo to fix first. */}
        {audio.supported && (
          <Button
            type="button"
            onClick={audio.toggle}
            disabled={transcribing}
            aria-pressed={audio.recording}
            variant="secondary"
            className={audio.recording ? 'border-action text-action' : undefined}
          >
            <VoiceIcon size={18} aria-hidden />
            {audio.recording ? 'Stop recording' : 'Voice note'}
          </Button>
        )}
        {/* A label styled as a button, around the real file input, so the
            keyboard reaches the input itself and the OS chooser opens as it
            always did.

            No `capture` attribute, deliberately. It is not a hint: it tells
            the browser to acquire from a camera and skip the file picker, so
            on Android it made the gallery unreachable. `accept` alone gets the
            OS chooser -- Camera, Gallery and Files -- so taking a photo still
            works. */}
        <label
          className={buttonVariants({
            variant: 'secondary',
            className: `cursor-pointer focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-action ${
              files.length >= MAX_IMAGES ? 'pointer-events-none opacity-45' : ''
            }`,
          })}
        >
          <PhotoIcon size={18} aria-hidden />
          Photos
          <span className="font-normal text-ink-2 tabular-nums">
            {files.length}/{MAX_IMAGES}
          </span>
          <input
            type="file"
            accept="image/*"
            multiple
            onChange={(e) => {
              addFiles(e.target.files)
              // Cleared so picking the same file again still fires a change
              // event -- otherwise removing a photo and re-adding it silently
              // does nothing.
              e.target.value = ''
            }}
            disabled={files.length >= MAX_IMAGES}
            className="sr-only"
          />
        </label>
      </div>

      {transcribing && (
        <p className="text-small text-ink-2">Transcribing. The text lands in the box above, ready to fix.</p>
      )}
      {audio.error && <p className="border-l-2 border-ink pl-3 text-small">{audio.error}</p>}

      {previewUrls.length > 0 && (
        <ul className="flex flex-wrap gap-2">
          {previewUrls.map((url, index) => (
            <li key={url} className="relative">
              <img
                src={url}
                alt={`Meal photo ${index + 1}`}
                className="size-16 rounded-control border border-rule object-cover"
              />
              <button
                type="button"
                onClick={() => removeFile(index)}
                aria-label={`Remove photo ${index + 1}`}
                className="absolute -top-2 -right-2 grid size-6 place-items-center rounded-tag bg-ink text-ground focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
              >
                <CloseIcon size={14} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}

      <LibraryFoodPicker
        foods={library}
        attached={attached}
        max={MAX_ATTACHED_FOODS}
        onAttach={attach}
        onDetach={detach}
      />

      <div className="flex flex-wrap gap-2">
        <Button onClick={() => analyze(false)} disabled={busy} className="flex-1">
          {analyzing ? 'Estimating…' : analysis ? 'Estimate again' : 'Estimate'}
        </Button>
        {analysis && (
          <Button variant="secondary" onClick={() => analyze(true)} disabled={busy} className="flex-1">
            Refine with my note
          </Button>
        )}
      </div>
      {analysis && (
        <p className="text-small text-ink-2">
          Refine adjusts this estimate to your note. Estimate again starts over, for new photos.
        </p>
      )}

      {unchangedRerun && (
        <div role="status" className="grid gap-2 border-l-2 border-ink pl-3 text-small">
          <p>
            Nothing has changed since this estimate: same note, photos and saved foods. Running it
            again uses one of today's AI estimates and usually moves the numbers only a few percent.
          </p>
          <div className="flex flex-wrap gap-2">
            {/* Same rule as the buttons above: a voice note still transcribing
                is about to change the note, so running now would send it without. */}
            <Button
              variant="secondary"
              onClick={() => analyze(unchangedRerun === 'refine', true)}
              disabled={busy}
            >
              Run it anyway
            </Button>
            <Button variant="ghost" onClick={dismissUnchangedRerun}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <EstimateStages
        state={progress}
        photos={files.length}
        hasNote={note.trim() !== ''}
        savedFoods={attached.length}
      />

      {/* Ink and words, never red (DESIGN.md, the No Red Rule). */}
      {error && <p className="border-l-2 border-ink pl-3 text-small">{error}</p>}

      <p className="text-small text-ink-2">
        Your note, photos and voice notes go to Google Gemini to be estimated.
      </p>

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
    </section>
  )
}
