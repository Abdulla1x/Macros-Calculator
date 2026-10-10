import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from 'react'
import { api } from '../api/client'
import { useAnalysisProgress } from '../hooks/useAnalysisProgress'
import { useAudioRecorder, voiceNoteFilename } from '../hooks/useAudioRecorder'
import type { AnalysisInputs } from '../lib/analysisInputs'
import { sameInputs } from '../lib/analysisInputs'
import { clearNoteDraft, readNoteDraft, writeNoteDraft } from '../lib/draft'
import { downscaleForUpload } from '../lib/photoDownscale'
import type { Food, MealAnalysisResponse } from '../types'
import { useToast } from '../ui/toast'
import { useLogPanel } from '../components/log/useLogPanel'

// Mirrors MAX_IMAGES in backend/app/routers/ai.py, which is the real limit --
// this copy exists only so the UI can stop you before a round trip does. If the
// two ever disagree the server still wins, and it answers 422.
export const MAX_IMAGES = 4

// Mirrors MAX_ATTACHED_FOODS in the same file, for the same reason and with the
// same rule about who wins. Each attached food is prompt tokens on every
// attempt, so this is a bill, not a preference.
export const MAX_ATTACHED_FOODS = 10

type Progress = ReturnType<typeof useAnalysisProgress>
type Audio = ReturnType<typeof useAudioRecorder>

interface AnalysisState {
  note: string
  setNote: (value: string | ((current: string) => string)) => void
  /** The description box, so a transcript or a correction can focus it. */
  noteRef: RefObject<HTMLTextAreaElement | null>
  files: File[]
  previewUrls: string[]
  addFiles: (picked: FileList | null) => void
  removeFile: (index: number) => void
  library: Food[]
  /** Fetch the saved foods for the picker (see the note on loadLibrary). */
  loadLibrary: () => void
  attached: Food[]
  attach: (food: Food) => void
  detach: (foodId: number) => void
  savedToLibrary: Record<string, string>
  markSaved: (itemName: string, savedAs: string) => void
  analysis: MealAnalysisResponse | null
  analyzing: boolean
  transcribing: boolean
  error: string | null
  setError: (error: string | null) => void
  unchangedRerun: 'again' | 'refine' | null
  dismissUnchangedRerun: () => void
  progress: Progress
  audio: Audio
  analyze: (refine: boolean, evenIfUnchanged?: boolean) => Promise<void>
  correctAssumption: (assumption: string) => void
  /** An estimate arrived while nothing was showing it (the Log button says
   *  "Ready" until it is looked at). */
  unseen: boolean
  /** Called by whatever shows the estimate, for as long as it is on screen.
   *  Returns the cleanup. */
  watch: () => () => void
  /** Clear everything for the next meal: note, photos, estimate, attachments. */
  reset: () => void
}

const AnalysisContext = createContext<AnalysisState | null>(null)

/** The AI estimate, held for the whole signed-in session rather than by the
 *  Log page.
 *
 *  An estimate takes ~19 s at the median and 43 s at the 95th percentile, and
 *  people move around the app while they wait. It used to live inside
 *  MealAnalyzer, so leaving the Log page threw away the photos, the call in
 *  flight and the answer it was about to give (only the note survived, through
 *  lib/draft.ts). Overhaul 0a made this a requirement: the analysis lives in
 *  app-level state, the Log button shows it working, and a note says when it
 *  is ready on any tab.
 *
 *  Mounted inside RequireAuth, so signing out unmounts it and nothing from one
 *  account's meal is left for the next. */
export function AnalysisProvider({ children }: { children: ReactNode }) {
  const toast = useToast()
  // The toasts' "View" opens the Log panel over whatever page is showing when
  // it is pressed, which may not be the one showing when the toast appeared;
  // the ref always holds the opener for the current page.
  const { open: openLog } = useLogPanel()
  const openLogRef = useRef(openLog)
  openLogRef.current = openLog
  const [note, setNote] = useState(readNoteDraft)
  const noteRef = useRef<HTMLTextAreaElement>(null)
  const [files, setFiles] = useState<File[]>([])
  const [previewUrls, setPreviewUrls] = useState<string[]>([])
  const [analysis, setAnalysis] = useState<MealAnalysisResponse | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [transcribing, setTranscribing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [library, setLibrary] = useState<Food[]>([])
  const [attached, setAttached] = useState<Food[]>([])
  // What each saved item was stored as, keyed by the name the model gave it.
  // The value is the name it went in under, which is not always the same one --
  // renaming before saving is the point of the form.
  //
  // Kept apart from `library` on purpose: that array is what LogMeal receives as
  // `libraryFoods`, which drives the per-row "use your saved numbers" offer.
  // Adding a food saved from this panel would make the page offer the estimate
  // back to itself a moment later, dressed up as an independent source.
  const [savedToLibrary, setSavedToLibrary] = useState<Record<string, string>>({})
  const [unseen, setUnseen] = useState(false)

  // What the estimate on screen was built from, and -- when a button was
  // pressed with nothing changed since -- which one, so the question can run it
  // anyway. A ref for the first: it is bookkeeping, nothing renders it.
  const lastSent = useRef<AnalysisInputs<File> | null>(null)
  const [unchangedRerun, setUnchangedRerun] = useState<'again' | 'refine' | null>(null)
  // Any edit answers the question by itself: the next press sends something new.
  useEffect(() => {
    setUnchangedRerun(null)
  }, [note, files, attached])

  // Owns everything about the wait: how much of the body has been sent, whether
  // the server turned out to be asleep, and when it is fair to say the model is
  // slow. This provider only says when a wait starts and when it ends.
  const progress = useAnalysisProgress()

  const audio = useAudioRecorder()
  const { blob: recording, durationMs, clear: clearRecording } = audio

  // How many screens are showing the estimate right now (the Log page, later
  // the Log panel). Zero when the answer lands means nobody saw it arrive, so
  // the Log button and a toast say so. A count, not a flag, so two mounts
  // overlapping during a route transition cannot clear each other.
  const watchers = useRef(0)
  const readyToast = useRef<number | null>(null)
  const watch = useCallback(() => {
    watchers.current += 1
    setUnseen(false)
    if (readyToast.current !== null) toast.dismiss(readyToast.current)
    return () => {
      watchers.current -= 1
    }
  }, [toast])

  // Fetched each time a screen opens the picker, not once per session: foods
  // added in Settings since should be attachable without a reload. A failure is
  // swallowed on purpose; the picker then has nothing to offer and says so, and
  // every other part of the analysis still works.
  const loadLibrary = useCallback(() => {
    api
      .getFoods()
      .then(setLibrary)
      .catch(() => undefined)
  }, [])

  // Mirrored to the draft on every keystroke. The draft now matters less (the
  // note survives a navigation in this provider), but it still carries the note
  // across a reload of the tab.
  useEffect(() => {
    writeNoteDraft(note)
  }, [note])

  // Each photo's upload-sized copy, started the moment it is picked rather than
  // when Analyze is pressed: the user is usually still typing or recording, so
  // by the time they press it the work is done. Keyed by the File itself, which
  // is also what makes a Refine re-run reuse it instead of shrinking again.
  //
  // Started from an effect, not from addFiles' state updater -- React runs
  // updaters twice under StrictMode, and an updater is meant to be pure. The
  // map makes the effect idempotent, and the same pass drops removed photos.
  const prepared = useRef(new Map<File, Promise<File>>())
  const preparedFor = (file: File) => {
    let upload = prepared.current.get(file)
    if (!upload) {
      upload = downscaleForUpload(file)
      prepared.current.set(file, upload)
    }
    return upload
  }
  useEffect(() => {
    const map = prepared.current
    for (const file of map.keys()) {
      if (!files.includes(file)) map.delete(file)
    }
    files.forEach(preparedFor)
    // preparedFor reads only the ref, so it cannot go stale.
  }, [files])

  // Every object URL created here must be revoked, or each re-pick leaks a
  // blob for the lifetime of the tab. The cleanup closes over the exact array
  // it created, so a fast second pick can't revoke the new URLs by mistake.
  // reset() empties `files`, which runs this cleanup too.
  useEffect(() => {
    const urls = files.map((item) => URL.createObjectURL(item))
    setPreviewUrls(urls)
    return () => urls.forEach(URL.revokeObjectURL)
  }, [files])

  // Transcribe the moment a recording lands, rather than sending the audio
  // along with the analysis: the text drops into the description where it can
  // be corrected first, so a misheard ingredient is a typo to fix instead of a
  // wrong number to notice afterwards.
  //
  // ⚠️ Each recording is sent exactly ONCE, enforced here rather than trusted to
  // the dependency list. A re-render used to re-run this effect and POST the
  // same audio a second time; every transcription is a Gemini call against a
  // daily quota of 20, so a duplicate is not harmless (see useAudioRecorder's
  // `clear`). For the same reason a re-run must not cancel the call already in
  // flight -- that would discard the one transcript that was paid for -- so the
  // only thing that drops a result is the provider going away (signing out).
  const sentRecording = useRef<Blob | null>(null)
  const mounted = useRef(true)
  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
    }
  }, [])

  useEffect(() => {
    if (!recording || sentRecording.current === recording) return
    sentRecording.current = recording

    // An accidental tap on the mic produces a fraction of a second of silence,
    // and the model will confidently transcribe that as a stray word rather
    // than nothing. Cheaper to catch here than to send it and let the user
    // wonder where "one" came from.
    if (durationMs < 500) {
      setError('That recording was too short — hold the button while you speak.')
      clearRecording()
      return
    }

    const transcribe = async () => {
      setTranscribing(true)
      setError(null)
      try {
        const form = new FormData()
        form.append('audio', recording, voiceNoteFilename(recording.type))
        const { transcript } = await api.transcribeVoiceNote(form)
        if (!mounted.current) return
        setNote((current) => (current.trim() ? `${current.trim()} ${transcript}` : transcript))
        noteRef.current?.focus()
      } catch (err) {
        if (mounted.current) {
          setError(err instanceof Error ? err.message : 'Could not transcribe that')
        }
      } finally {
        if (mounted.current) {
          setTranscribing(false)
          // Either way the recording is spent -- dropping it lets the user just
          // record again instead of having to discard a failed one first.
          clearRecording()
        }
      }
    }

    void transcribe()
  }, [recording, durationMs, clearRecording])

  // Appended, not replaced: on a phone the gallery picker is usually opened
  // once per photo, so replacing would make the second pick silently discard
  // the first. Trimmed to the cap here rather than refusing the whole batch.
  const addFiles = (picked: FileList | null) => {
    // Copied out of the FileList *now*, not inside the state updater below.
    // The change handler resets input.value so re-picking the same file still
    // fires an event, and that reset empties the live FileList -- by the time
    // React ran the updater there was nothing left in it, so every selection
    // silently vanished. An array snapshot is unaffected.
    const chosen = picked ? Array.from(picked) : []
    if (chosen.length === 0) return
    setError(null)
    setFiles((current) => {
      const room = MAX_IMAGES - current.length
      if (room <= 0) {
        setError(`That's the limit — ${MAX_IMAGES} photos per analysis.`)
        return current
      }
      const accepted = chosen.slice(0, room)
      if (accepted.length < chosen.length) {
        setError(`Only the first ${accepted.length} were added — ${MAX_IMAGES} photos max.`)
      }
      return [...current, ...accepted]
    })
  }

  const removeFile = (index: number) => {
    setFiles((current) => current.filter((_, position) => position !== index))
    setError(null)
  }

  const analyze = async (refine: boolean, evenIfUnchanged = false) => {
    if (files.length === 0 && !note.trim()) {
      setError('Describe the meal, record a voice note, or add a photo first.')
      return
    }
    // Pressing either button with nothing changed is a re-roll: one of the
    // day's AI calls for an answer that moves by the model's own noise (~3% in
    // the 2026-10-05 audit). Asked, not refused -- it is the user's call.
    const inputs = { note, photos: files, foodIds: attached.map((food) => food.id) }
    if (!evenIfUnchanged && analysis && lastSent.current && sameInputs(inputs, lastSent.current)) {
      setUnchangedRerun(refine ? 'refine' : 'again')
      return
    }
    setUnchangedRerun(null)
    setAnalyzing(true)
    setUnseen(false)
    setError(null)
    // Photos are what make a body worth showing a bar for. A note-only analysis
    // uploads a few hundred bytes and goes straight to waiting on the model.
    // Shrunk on this device first (lib/photoDownscale.ts). Usually already
    // finished, since it started when each photo was picked; it never rejects,
    // and anything it cannot shrink comes back as the original.
    const uploads = await Promise.all(files.map(preparedFor))
    const hooks = progress.start(uploads.length > 0)
    try {
      const form = new FormData()
      // Repeated under one field name -- the backend reads `image` as a list.
      uploads.forEach((item) => form.append('image', item))
      // Ids only: the server reads the macros out of the library itself, so a
      // request cannot claim a saved food has numbers it does not have.
      attached.forEach((food) => form.append('food_id', String(food.id)))
      if (note.trim()) form.append('text', note.trim())
      if (refine && analysis) form.append('prior_analysis', JSON.stringify(analysis))
      const result = await api.analyzeMeal(form, hooks)
      if (!mounted.current) return
      setAnalysis(result)
      // Only an estimate that arrived counts: after a failure, trying again
      // with the same inputs is exactly what the user should be able to do.
      lastSent.current = inputs
      // The items are all new, so the "saved ✓" marks against the old ones no
      // longer describe anything on screen. Refining in particular re-portions
      // and often renames, so even a name that survives is a different estimate.
      setSavedToLibrary({})
      if (watchers.current === 0) {
        setUnseen(true)
        readyToast.current = toast.show({
          text: 'Your estimate is ready.',
          action: { label: 'View', onSelect: () => openLogRef.current() },
        })
      }
    } catch (err) {
      if (!mounted.current) return
      setError(err instanceof Error ? err.message : 'Analysis failed')
      // Nobody is looking at the Log page to see the error there, and the Log
      // button has no "failed" state, so the toast is the only way they learn.
      if (watchers.current === 0) {
        toast.show({
          text: "The estimate didn't come through.",
          action: { label: 'See why', onSelect: () => openLogRef.current() },
        })
      }
    } finally {
      if (mounted.current) {
        setAnalyzing(false)
        progress.finish()
      }
    }
  }

  const correctAssumption = (assumption: string) => {
    setNote((current) => {
      const prefix = current.trim() ? `${current.trim()}\n` : ''
      return `${prefix}Correction: ${assumption} → `
    })
    noteRef.current?.focus()
  }

  const reset = () => {
    // Emptying `files` revokes the preview URLs (the effect above) and drops the
    // prepared uploads. The draft is cleared too, or a reload would hand the
    // next meal the description of the one just saved.
    setFiles([])
    setNote('')
    clearNoteDraft()
    setAnalysis(null)
    setAttached([])
    setSavedToLibrary({})
    setUnchangedRerun(null)
    setError(null)
    setUnseen(false)
    lastSent.current = null
  }

  return (
    <AnalysisContext.Provider
      value={{
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
        attach: (food) =>
          setAttached((current) =>
            current.length >= MAX_ATTACHED_FOODS || current.some((f) => f.id === food.id)
              ? current
              : [...current, food],
          ),
        detach: (foodId) => setAttached((current) => current.filter((food) => food.id !== foodId)),
        savedToLibrary,
        markSaved: (itemName, savedAs) =>
          setSavedToLibrary((current) => ({ ...current, [itemName]: savedAs })),
        analysis,
        analyzing,
        transcribing,
        error,
        setError,
        unchangedRerun,
        dismissUnchangedRerun: () => setUnchangedRerun(null),
        progress,
        audio,
        analyze,
        correctAssumption,
        unseen,
        watch,
        reset,
      }}
    >
      {children}
    </AnalysisContext.Provider>
  )
}

export function useAnalysis(): AnalysisState {
  const state = useContext(AnalysisContext)
  if (!state) throw new Error('useAnalysis must be used within AnalysisProvider')
  return state
}
