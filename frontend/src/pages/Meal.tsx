import { useCallback, useEffect, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { api } from '../api/client'
import ShareCodePanel from '../components/ShareCodePanel'
import ScreenBar from '../components/shell/ScreenBar'
import { useLogPanel } from '../components/log/useLogPanel'
import { useLiveMessage } from '../hooks/useLiveMessage'
import { localIsoDate } from '../lib/dates'
import { announceMealsChanged, onMealsChanged } from '../lib/mealEvents'
import { mealTimeLabel, viewedDay } from '../lib/today'
import { useSettings } from '../settings/SettingsContext'
import type { Meal as MealType } from '../types'
import Block from '@/ui/block'
import { Button } from '@/ui/button'
import { DeleteIcon, EditIcon, KeepIcon, LogAgainIcon, ShareIcon } from '@/ui/icons'
import { RowButton } from '@/ui/row'
import { Stat, StatGrid } from '@/ui/stat'
import { useToast } from '@/ui/toast'

const n = (value: number) => Math.round(value).toLocaleString()

type Loaded = { kind: 'loading' } | { kind: 'found'; meal: MealType } | { kind: 'gone' } | { kind: 'failed' }

/** One meal, opened from its row on Today (0a: meal rows open a meal screen).
 *  Everything you can do to a logged meal is here, as full-size rows, instead
 *  of three tiny glyphs on every row of the list (UA-13).
 *
 *  The row hands the meal over in router state, so the screen draws at once;
 *  opened any other way (a reload, a bookmark), it finds the meal in its day,
 *  since there is no endpoint for one meal. */
export default function Meal() {
  const params = useParams()
  const today = localIsoDate()
  const day = viewedDay(params.date ?? null, today)
  const id = Number(params.id)
  const handed = (useLocation().state as { meal?: MealType } | null)?.meal
  const navigate = useNavigate()
  const { settings } = useSettings()
  const { open: openLog } = useLogPanel()
  const toast = useToast()
  const [loaded, setLoaded] = useState<Loaded>(() =>
    handed?.id === id ? { kind: 'found', meal: handed } : { kind: 'loading' },
  )
  const [code, setCode] = useState<string | null>(null)
  const [message, setMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  useLiveMessage(error)

  const back = day === today ? '/' : `/?day=${day}`

  const load = useCallback(() => {
    api
      .getMeals(day)
      .then((meals) => {
        const meal = meals.find((each) => each.id === id)
        setLoaded(meal ? { kind: 'found', meal } : { kind: 'gone' })
      })
      .catch(() => setLoaded((now) => (now.kind === 'found' ? now : { kind: 'failed' })))
  }, [day, id])

  // Always re-read, even when the row handed the meal over: the state can be
  // older than the server (another tab, an edit made through the Log panel).
  useEffect(load, [load])
  useEffect(() => onMealsChanged(() => load()), [load])

  if (loaded.kind !== 'found') {
    return (
      <div className="mx-auto grid max-w-[760px] grid-cols-[minmax(0,1fr)]">
        <ScreenBar title="Meal" back={back} backLabel="Back to Today" />
        <Block>
          {loaded.kind === 'loading' ? (
            <span aria-hidden="true" className="h-24 rounded-control bg-track motion-safe:animate-pulse" />
          ) : loaded.kind === 'gone' ? (
            <p className="text-small text-ink-2">This meal isn't on this day any more. It may have been deleted or moved.</p>
          ) : (
            <p role="alert" className="border-l-2 border-ink pl-3 text-small">
              Couldn't load this meal. Check your connection, then try again.{' '}
              <button type="button" onClick={load} className="font-semibold underline underline-offset-3">
                Retry
              </button>
            </p>
          )}
        </Block>
      </div>
    )
  }

  const meal = loaded.meal
  const logged = mealTimeLabel(meal, settings?.show_meal_times ?? true)

  // Copied to TODAY, whichever day it came from: "log it again" means
  // "I'm eating this again", and that is now.
  const logAgain = async () => {
    setBusy(true)
    setError(null)
    try {
      await api.createMeal({
        date: today,
        name: meal.name,
        calories: meal.calories,
        protein: meal.protein,
        carbs: meal.carbs,
        fat: meal.fat,
      })
      announceMealsChanged({ date: today })
      toast.show({ text: `Logged "${meal.name}" again for today.` })
      navigate('/')
    } catch (err) {
      setError(err instanceof Error ? err.message : "That didn't save. Check your connection, then try again.")
      setBusy(false)
    }
  }

  // Minted on demand: a code is derived from the row, so there is nothing to
  // keep in sync when the row changes.
  const share = async () => {
    setError(null)
    try {
      setCode((await api.shareMeal(meal.id)).code)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't make a code. Try again.")
    }
  }

  // A logged meal keeps no ingredients, so the saved meal holds its totals;
  // re-logging it fills one row with them, which the form already handles.
  const keep = async () => {
    setError(null)
    setMessage(null)
    try {
      const saved = await api.saveMealTemplate({
        name: meal.name,
        calories: meal.calories,
        protein: meal.protein,
        carbs: meal.carbs,
        fat: meal.fat,
        items: [],
      })
      // Saving over a saved meal throws away its ingredient list, and there
      // is no undo, so say which one happened.
      setMessage(saved.created ? 'Kept as a saved meal.' : `Replaced your saved meal "${meal.name}".`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Saving the meal failed.')
    }
  }

  return (
    <div className="mx-auto grid max-w-[760px] grid-cols-[minmax(0,1fr)]">
      <ScreenBar title="Meal" back={back} backLabel="Back to Today" />

      {/* The name in full here, where it can wrap: the bar above would cut a
          long one off, and it is the one thing this screen is about. */}
      <Block label={logged ? `Logged ${logged}` : undefined}>
        <h2 className="text-title text-pretty">{meal.name}</h2>
        <p className="flex items-end gap-2">
          <span className="text-display-number text-[72px]">{n(meal.calories)}</span>
          <span className="pb-1.5 text-small text-ink-2">kcal</span>
        </p>
        <StatGrid>
          <Stat label="Protein" unit="g">
            {n(meal.protein)}
          </Stat>
          {settings?.track_carbs && meal.carbs !== null && (
            <Stat label="Carbs" unit="g">
              {n(meal.carbs)}
            </Stat>
          )}
          {settings?.track_fat && meal.fat !== null && (
            <Stat label="Fat" unit="g">
              {n(meal.fat)}
            </Stat>
          )}
        </StatGrid>
      </Block>

      {code && <ShareCodePanel label={meal.name} code={code} onClose={() => setCode(null)} />}

      <Block>
        {error && (
          <p role="alert" className="border-l-2 border-ink pl-3 text-small">
            {error}
          </p>
        )}
        {message && (
          <p role="status" className="text-small text-ink-2">
            {message}
          </p>
        )}
        <div className="divide-y divide-rule">
          <RowButton
            icon={<EditIcon size={18} />}
            label="Edit"
            chevron
            onClick={() => openLog('hand', { date: null, state: { editMeal: meal } })}
          />
          <RowButton
            icon={<LogAgainIcon size={18} />}
            label="Log it again"
            detail="Adds a copy to today"
            disabled={busy}
            onClick={logAgain}
          />
          <RowButton
            icon={<ShareIcon size={18} />}
            label="Share as a code"
            detail="Anyone with the code can add it to their log"
            onClick={share}
          />
          <RowButton icon={<KeepIcon size={18} />} label="Keep as a saved meal" onClick={keep} />
        </div>
        {/* No "are you sure?": Today holds the deletion for ten seconds with
            Undo, which is a better answer to a mis-tap than a question asked
            every time. */}
        <Button
          variant="ghost"
          className="mt-2 w-full"
          onClick={() => navigate(back, { state: { deleteMeal: meal } })}
        >
          <DeleteIcon size={18} aria-hidden="true" />
          Delete
        </Button>
      </Block>
    </div>
  )
}
