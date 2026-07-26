import { useEffect, useRef, useState } from 'react'

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
  const chunksRef = useRef<BlobPart[]>([])
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
    const recorder = new MediaRecorder(stream)
    chunksRef.current = []
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunksRef.current.push(event.data)
    }
    recorder.onstop = () => {
      setDurationMs(Date.now() - startedAtRef.current)
      setBlob(new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' }))
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
