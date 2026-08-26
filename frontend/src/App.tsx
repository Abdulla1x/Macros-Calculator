import { Route, Routes } from 'react-router-dom'
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
import Settings from './pages/Settings'
import Signup from './pages/Signup'
import Weight from './pages/Weight'
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
          <Route path="/settings" element={<Settings />} />
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
