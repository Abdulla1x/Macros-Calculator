import { useEffect, useRef, useState } from 'react'

// Extensions that don't match their mime subtype.
const EXTENSION_OVERRIDES: Record<string, string> = {
  mpeg: 'mp3',
  'x-wav': 'wav',
  'x-m4a': 'm4a',
}

/** A filename matching the audio we actually recorded.
 *
 * The mime type on the blob is what the backend forwards to Gemini, so this is
 * only for logs and error messages — but a `.webm` name on an MP4 recording
 * sends whoever reads those logs chasing the wrong bug. */
export function voiceNoteFilename(mimeType: string): string {
  // split() always returns at least one element, so [0] is never actually
  // undefined -- but ?? '' states that in code instead of asserting it away,
  // and costs nothing.
  const base = mimeType.split(';')[0] ?? ''
  const subtype = base.trim().toLowerCase().split('/')[1] ?? ''
  const extension = EXTENSION_OVERRIDES[subtype] ?? subtype
  return `voice-note.${/^[a-z0-9]+$/.test(extension) ? extension : 'webm'}`
}

/** Records a voice note with MediaRecorder and hands back the raw audio.
 *
 * Replaces the old Web Speech API dictation, which silently didn't exist in
 * Firefox and parts of mobile Safari. MediaRecorder is available everywhere we
 * support, and sending the audio itself lets Gemini hear the food names rather
 * than trusting on-device speech recognition to spell them. */
export function useAudioRecorder() {
  const [recording, setRecording] = useState(false)
  const [blob, setBlob] = useState<Blob | null>(null)
  const [durationMs, setDurationMs] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const recorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const startedAtRef = useRef(0)

  const supported =
    typeof window !== 'undefined' &&
    typeof window.MediaRecorder !== 'undefined' &&
    Boolean(navigator.mediaDevices?.getUserMedia)

  // Releasing the mic matters: the browser shows a recording indicator for as
  // long as any track is live, even after the component is gone.
  const stopTracks = () => {
    recorderRef.current?.stream.getTracks().forEach((track) => track.stop())
    recorderRef.current = null
  }

  useEffect(() => () => stopTracks(), [])

  const start = async () => {
    if (!supported) return
    setError(null)
    let stream: MediaStream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true })
    } catch {
      setError('Microphone access was blocked. Allow it, or type a description instead.')
      return
    }
    // The browser default is deliberate. Chromium can only record WebM or MP4
    // anyway, and the WebM it produces is what Gemini is known to accept.
    const recorder = new MediaRecorder(stream)
    chunksRef.current = []
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data)
    }
    recorder.onstop = () => {
      setDurationMs(Date.now() - startedAtRef.current)
      // Some browsers leave recorder.mimeType empty; the chunks still carry the
      // real type, and that's what the backend forwards to Gemini.
      const type =
        recorder.mimeType || chunksRef.current[0]?.type || 'audio/webm'
      setBlob(new Blob(chunksRef.current, { type }))
      stopTracks()
      setRecording(false)
    }
    recorderRef.current = recorder
    startedAtRef.current = Date.now()
    recorder.start()
    setRecording(true)
  }

  const stop = () => recorderRef.current?.stop()

  const toggle = () => {
    if (recording) stop()
    else void start()
  }

  const clear = () => {
    setBlob(null)
    setError(null)
  }

  return { supported, recording, blob, durationMs, error, toggle, clear }
}
