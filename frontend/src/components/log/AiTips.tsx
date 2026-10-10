import { useState } from 'react'
import { areAiTipsDismissed, dismissAiTips } from '../../lib/dismissals'
import { CloseIcon } from '@/ui/icons'

/** Three things the AI cannot see, above the AI box until dismissed (UA-25).
 *
 *  One short card rather than a tutorial at signup: it sits where the
 *  estimate is made, says what moves accuracy most, and goes away for good
 *  with one tap. The order is the order of impact on the evaluation: a note
 *  with weights halves the error, hidden extras are what photos miss, and an
 *  attached saved food turns a guess into a fact. */
export default function AiTips() {
  const [dismissed, setDismissed] = useState(areAiTipsDismissed)
  if (dismissed) return null
  return (
    <aside aria-labelledby="ai-tips-title" className="relative grid gap-2 rounded-control border-[1.5px] border-ink p-3 pr-12">
      <h4 id="ai-tips-title" className="text-[14.5px] font-bold">
        Three things the AI can't see
      </h4>
      <ul className="grid gap-1.5 text-small">
        <li>
          <b>Weights.</b> “150 g chicken” beats any photo, and a voice note counts.
        </li>
        <li>
          <b>Hidden extras.</b> Oil, butter, sauce and sugar barely show in photos, so say them.
        </li>
        <li>
          <b>Your saved foods.</b> Attach the packaged ones and their numbers count as facts.
        </li>
      </ul>
      <button
        type="button"
        onClick={() => {
          dismissAiTips()
          setDismissed(true)
        }}
        aria-label="Dismiss the tips"
        className="absolute top-1 right-1 grid size-11 place-items-center rounded-control text-ink-2 hover:text-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-action"
      >
        <CloseIcon size={18} aria-hidden />
      </button>
    </aside>
  )
}
