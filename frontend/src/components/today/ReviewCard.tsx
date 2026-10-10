import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import { addDays, parseIsoDate } from '../../lib/dates'
import { reviewHeadline } from '../../lib/review'
import type { WeeklyReview } from '../../types'
import { Button } from '@/ui/button'
import Block from '@/ui/block'

/** The weekly review, brought up on Today on review day (0a: "Review appears
 *  as a card on review day"). One sentence from the review's own checks, and
 *  the way in. The week is the seven days before today, the same window the
 *  review page uses. If the review can't be read, the card still offers the
 *  way in rather than inventing a summary. */
export default function ReviewCard({ today }: { today: string }) {
  const end = addDays(today, -1)
  const [review, setReview] = useState<WeeklyReview | null>(null)

  useEffect(() => {
    let live = true
    api
      .getReview(end)
      .then((next) => live && setReview(next))
      .catch(() => live && setReview(null))
    return () => {
      live = false
    }
  }, [end])

  const span = (iso: string) => parseIsoDate(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short' })

  return (
    <Block label="Weekly review" value={review ? `${span(review.window_start)} to ${span(review.window_end)}` : undefined}>
      <p>
        <b className="font-semibold">Your week is in.</b> {review ? reviewHeadline(review) : null}
      </p>
      <div>
        <Button asChild>
          <Link to="/review">Open the review</Link>
        </Button>
      </div>
    </Block>
  )
}
