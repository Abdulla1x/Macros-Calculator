import type { ComponentType } from 'react'
import { LazyMotion, MotionConfig } from 'motion/react'
import {
  createBrowserRouter,
  createRoutesFromElements,
  Navigate,
  Route,
  RouterProvider,
  useLocation,
  useRouteError,
} from 'react-router-dom'
import Announcer from './components/Announcer'
import { CrashScreen } from './components/ErrorBoundary'
import Layout from './components/Layout'
import LogRedirect from './components/log/LogRedirect'
import RequireAdmin from './components/RequireAdmin'
import RequireAuth from './components/RequireAuth'
import ForgotPassword from './pages/ForgotPassword'
import Login from './pages/Login'
import NotFound from './pages/NotFound'
import ResetPassword from './pages/ResetPassword'
import Signup from './pages/Signup'
import { DURATION, EASE, loadMotionFeatures } from './lib/motion'
import { isReloadingForNewVersion, isStaleChunkError, reloadForNewVersion } from './lib/staleChunk'
import { SettingsProvider } from './settings/SettingsContext'
import { AnalysisProvider } from './analysis/AnalysisContext'
import { ToastProvider } from './ui/toast'

/** The route errorElement: the same crash screen ErrorBoundary shows.
 *
 * A data router catches anything thrown while rendering a route in its own
 * boundary, so those errors never reach ErrorBoundary in main.tsx. Without
 * this they would land on React Router's built-in developer error page. */
function RouteError() {
  const error = useRouteError()
  // The address the router was heading to: the errorElement renders AT the
  // failed destination, even when the browser's address bar has not moved.
  const { pathname, search, hash } = useLocation()
  // A page's file went missing in a deploy (see lib/staleChunk.ts): load the
  // destination afresh on the new version instead of reporting a crash,
  // unless that was already tried a moment ago. Every lazy import in the app
  // is a route's, so this is the one place such a failure surfaces.
  if (
    isStaleChunkError(error) &&
    (isReloadingForNewVersion() || reloadForNewVersion(pathname + search + hash))
  ) {
    return null
  }
  console.error('Unhandled route error:', error)
  return <CrashScreen error={error} />
}

/** One downloadable piece per page (route-level code splitting).
 *
 * The app used to ship as a single ~900 KB script, so the login page also
 * carried the charts library, the meal analyzer and Admin. Each page below
 * now loads its own piece the first time it is opened. The router's own
 * `lazy` rather than React.lazy + Suspense: a navigation waits for the next
 * page's piece while the current page stays on screen, so there is no
 * loading flash between pages, and a failed load lands in RouteError above,
 * where the stale-deploy case is recovered.
 *
 * NOT lazy: the auth pages, NotFound and the shell (RequireAuth, Layout,
 * SettingsProvider). They are small and they are the first screen, so a new
 * visitor's first paint needs no second request. */
type PageModule = { default: ComponentType }
const page = (load: () => Promise<PageModule>) => async () => ({ Component: (await load()).default })

/** A data router (createBrowserRouter) rather than <BrowserRouter> + <Routes>.
 *
 * The routes are unchanged; what the switch buys is useBlocker, which only
 * works under a data router. Settings uses it to ask before an in-app
 * navigation drops an unsaved draft (beforeunload only ever covered a reload
 * or a closed tab). Built once at module scope, as the router expects: it
 * owns the history listener, and re-creating it per render would reset it.
 *
 * Still written as JSX, through createRoutesFromElements, so the tree and the
 * reasoning attached to each route read exactly as they did. */
const router = createBrowserRouter(
  createRoutesFromElements(
    // hydrateFallbackElement covers the first load of a lazy page: the router
    // waits for its piece before the first render. Empty on purpose: it is a
    // few milliseconds on the ground colour, and a spinner would only flash.
    <Route errorElement={<RouteError />} hydrateFallbackElement={<></>}>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route element={<RequireAuth />}>
        {/* Inside RequireAuth, so the settings fetch only ever runs with a
            token in hand; outside Layout's children, so all five pages read
            one shared copy instead of fetching their own. */}
        {/* AnalysisProvider holds the AI estimate for the whole session, so it
            survives moving between pages (overhaul 0a); it tells the user an
            estimate is ready through the toast, hence the order. */}
        <Route
          element={
            <SettingsProvider>
              <ToastProvider>
                <AnalysisProvider>
                  <Layout />
                </AnalysisProvider>
              </ToastProvider>
            </SettingsProvider>
          }
        >
          <Route index lazy={page(() => import('./pages/Today'))} />
          {/* Log is a panel over the current page now (components/log/), not a
              page; the address only redirects there. */}
          <Route path="/log" element={<LogRedirect />} />
          <Route path="/weight" lazy={page(() => import('./pages/Weight'))} />
          <Route path="/analytics" lazy={page(() => import('./pages/Analytics'))} />
          {/* In the tab bar, unlike /whats-new below. It was kept out at first on
              an ESTIMATE -- that a sixth cell would leave less room than the
              word "Dashboard" needs -- and the estimate was wrong. Measured:
              six cells are 60px at 360px and "Dashboard" renders at exactly
              60px, so it fits, and the labels shrink to 10px below 360px where
              they would not. The dashboard's seven-day card still links here
              too, because it covers exactly this window. */}
          <Route path="/review" lazy={page(() => import('./pages/Review'))} />
          {/* Settings is a shell around five panels rather than one page. The
              shell owns the draft and the Save bar; each panel is a real
              address, so the dashboard's deep link into the calorie planner
              lands somewhere specific and back/forward walk the sections.

              Each panel is its own lazy piece now. This note used to forbid
              that, because a tab asking for a piece a deploy had removed would
              white-screen. Tabs the service worker controls are reloaded onto
              the new version by autoUpdate; the rest (first visit, hard
              refresh, worker blocked) reload once on that error instead
              (RouteError + lib/staleChunk.ts). */}
          <Route path="/settings" lazy={page(() => import('./pages/Settings'))}>
            <Route index element={<Navigate to="/settings/goals" replace />} />
            <Route path="goals" lazy={page(() => import('./pages/settings/GoalsPanel'))} />
            <Route path="body" lazy={page(() => import('./pages/settings/BodyPanel'))} />
            <Route path="trackers" lazy={page(() => import('./pages/settings/TrackersPanel'))} />
            <Route path="food" lazy={page(() => import('./pages/settings/LibraryPanel'))} />
            {/* Absent from the tab bar by design; see tabs.ts. */}
            <Route path="account" lazy={page(() => import('./pages/settings/AccountPanel'))} />
          </Route>
          {/* Not in nav, same posture as /admin: it is somewhere you go when a
              note points you there, not a fifth thing to choose between every
              day. Reached from the What's new pop-up and from Settings ->
              Account. */}
          <Route path="/whats-new" lazy={page(() => import('./pages/WhatsNew'))} />
          {/* Deliberately absent from Layout's nav: only the operator uses it.
              This used to also cite the nav degrading to emoji-only below `sm`;
              that is no longer true — the tab bar labels every item at every
              width — so the operator-only reason is the whole reason now.
              Reached by typing the URL; guarded here for display and by
              require_admin on the server for real. */}
          <Route element={<RequireAdmin />}>
            <Route path="/admin" lazy={page(() => import('./pages/Admin'))} />
          </Route>
          {/* Last, so every real route above wins. Inside Layout so an
              unmatched address still arrives with the nav to leave by. */}
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Route>,
  ),
)

export default function App() {
  return (
    <>
      {/* Outside the router on purpose. A live region has to be in the document
          BEFORE the text it announces, and it has to survive navigation -- one
          mounted per route would be recreated on every route change, which is
          the same silence it exists to prevent. sr-only takes it out of flow, so
          it costs no layout here. */}
      <Announcer />
      {/* Motion, set up once for the whole app:
          - LazyMotion + `m` elements instead of `motion` ones: the animation
            features (about 15 KB) arrive as their own piece after first
            paint, and `strict` makes a stray full-size `motion.div` throw in
            development instead of quietly pulling ~34 KB back in.
          - reducedMotion="user" honours the phone's reduce-motion setting in
            every Motion animation (UA-16), without each one checking.
          - DESIGN.md's defaults, so an animation that names no timing gets the
            house one: 240 ms on the exponential ease-out. */}
      <LazyMotion features={loadMotionFeatures} strict>
        <MotionConfig reducedMotion="user" transition={{ duration: DURATION.base, ease: EASE }}>
          <RouterProvider router={router} />
        </MotionConfig>
      </LazyMotion>
    </>
  )
}
