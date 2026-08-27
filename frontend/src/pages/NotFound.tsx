import { Link, useLocation } from 'react-router-dom'
import { primaryButtonClass } from '../components/ui/Button'

/** What an unmatched URL renders.
 *
 * Before this route existed, a typed or stale path fell through every branch
 * and `<Routes>` matched nothing: signed in, that drew the nav above a blank
 * area; signed out, a white screen. Neither said anything had gone wrong, so
 * both read as the app being broken rather than the address being wrong.
 *
 * Only registered inside the authenticated Layout, which is enough: RequireAuth
 * redirects a signed-out visitor to /login before Layout renders, so there is
 * no unauthenticated path left for a second catch-all to cover.
 */
export default function NotFound() {
  const { pathname } = useLocation()

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-bold">Page not found</h1>
        <p className="text-sm text-slate-400">
          Nothing lives at <code className="text-slate-300">{pathname}</code>.
        </p>
      </header>
      <p className="text-sm text-slate-400">
        If you followed a link from inside the app, that is a bug worth
        reporting. If you typed the address, check it for a typo.
      </p>
      <Link
        to="/"
        className={`${primaryButtonClass} inline-block px-4 py-2`}
      >
        Back to the dashboard
      </Link>
    </div>
  )
}
