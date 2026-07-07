import { useEffect, useRef, useState } from 'react'

interface RecognitionEventLike {
  results: ArrayLike<ArrayLike<{ transcript: string }>>
}

interface RecognitionLike {
  continuous: boolean
  interimResults: boolean
  lang: string
  onresult: ((event: RecognitionEventLike) => void) | null
  onend: (() => void) | null
  onerror: (() => void) | null
  start(): void
  stop(): void
  abort(): void
}

type RecognitionCtor = new () => RecognitionLike

const getCtor = (): RecognitionCtor | undefined => {
  const w = window as unknown as {
    SpeechRecognition?: RecognitionCtor
    webkitSpeechRecognition?: RecognitionCtor
  }
  return w.SpeechRecognition ?? w.webkitSpeechRecognition
}

/** Browser dictation (Web Speech API). Voice never leaves the client — the
 * transcript is handed to `onText` as plain text. */
export function useDictation(onText: (transcript: string) => void) {
  const [listening, setListening] = useState(false)
  const recognitionRef = useRef<RecognitionLike | null>(null)
  const supported = typeof window !== 'undefined' && Boolean(getCtor())

  useEffect(() => () => recognitionRef.current?.abort(), [])

  const start = () => {
    const Ctor = getCtor()
    if (!Ctor) return
    const recognition = new Ctor()
    recognition.continuous = false
    recognition.interimResults = false
    recognition.lang = navigator.language || 'en-US'
    recognition.onresult = (event) => {
      const transcript = Array.from(event.results, (result) => result[0].transcript)
        .join(' ')
        .trim()
      if (transcript) onText(transcript)
    }
    recognition.onend = () => setListening(false)
    recognition.onerror = () => setListening(false)
    recognitionRef.current = recognition
    recognition.start()
    setListening(true)
  }

  const toggle = () => {
    if (listening) recognitionRef.current?.stop()
    else start()
  }

  return { supported, listening, toggle }
}
