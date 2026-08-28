import { Navigate, Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import RequireAdmin from './components/RequireAdmin'
import RequireAuth from './components/RequireAuth'
import Admin from './pages/Admin'
import Analytics from './pages/Analytics'
import Dashboard from './pages/Dashboard'
import ForgotPassword from './pages/ForgotPassword'
import Login from './pages/Login'
import LogMeal from './pages/LogMeal'
import NotFound from './pages/NotFound'
import ResetPassword from './pages/ResetPassword'
import Review from './pages/Review'
import Settings from './pages/Settings'
import Signup from './pages/Signup'
import Weight from './pages/Weight'
import WhatsNew from './pages/WhatsNew'
import AccountPanel from './pages/settings/AccountPanel'
import BodyPanel from './pages/settings/BodyPanel'
import GoalsPanel from './pages/settings/GoalsPanel'
import LibraryPanel from './pages/settings/LibraryPanel'
import TrackersPanel from './pages/settings/TrackersPanel'
import { SettingsProvider } from './settings/SettingsContext'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />
      <Route element={<RequireAuth />}>
        {/* Inside RequireAuth, so the settings fetch only ever runs with a
            token in hand; outside Layout's children, so all five pages read
            one shared copy instead of fetching their own. */}
        <Route
          element={
            <SettingsProvider>
              <Layout />
            </SettingsProvider>
          }
        >
          <Route index element={<Dashboard />} />
          <Route path="/log" element={<LogMeal />} />
          <Route path="/weight" element={<Weight />} />
          <Route path="/analytics" element={<Analytics />} />
          {/* Not in the tab bar, the same posture as /whats-new below: the bar
              is a fixed five-column grid and a sixth cell drops each one from
              ~72px to ~60px at 360px, which is narrower than the word
              "Dashboard" renders at. Reached from the dashboard's own
              seven-day card, which covers exactly this window, and from
              Analytics. */}
          <Route path="/review" element={<Review />} />
          {/* Settings is a shell around five panels rather than one page. The
              shell owns the draft and the Save bar; each panel is a real
              address, so the dashboard's deep link into the calorie planner
              lands somewhere specific and back/forward walk the sections.

              Deliberately NOT React.lazy, however much a tab split invites it:
              the service worker registers with autoUpdate, which implies
              skipWaiting + clientsClaim, so a new worker can take control while
              an old page is still open. There are no dynamic imports anywhere
              in this app today, so there are no chunks to 404 -- lazy-loading
              these tabs is exactly what would turn a stale session into a white
              screen on a tab click. */}
          <Route path="/settings" element={<Settings />}>
            <Route index element={<Navigate to="/settings/goals" replace />} />
            <Route path="goals" element={<GoalsPanel />} />
            <Route path="body" element={<BodyPanel />} />
            <Route path="trackers" element={<TrackersPanel />} />
            <Route path="food" element={<LibraryPanel />} />
            {/* Absent from the tab bar by design; see tabs.ts. */}
            <Route path="account" element={<AccountPanel />} />
          </Route>
          {/* Not in nav, same posture as /admin: it is somewhere you go when a
              note points you there, not a fifth thing to choose between every
              day. Reached from the What's new pop-up and from Settings ->
              Account. */}
          <Route path="/whats-new" element={<WhatsNew />} />
          {/* Deliberately absent from Layout's nav: only the operator uses it.
              This used to also cite the nav degrading to emoji-only below `sm`;
              that is no longer true — the tab bar labels every item at every
              width — so the operator-only reason is the whole reason now.
              Reached by typing the URL; guarded here for display and by
              require_admin on the server for real. */}
          <Route element={<RequireAdmin />}>
            <Route path="/admin" element={<Admin />} />
          </Route>
          {/* Last, so every real route above wins. Inside Layout so an
              unmatched address still arrives with the nav to leave by. */}
          <Route path="*" element={<NotFound />} />
        </Route>
      </Route>
    </Routes>
  )
}
