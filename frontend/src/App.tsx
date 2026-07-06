import { Route, Routes } from 'react-router-dom'
import Layout from './components/Layout'
import Analytics from './pages/Analytics'
import Dashboard from './pages/Dashboard'
import LogMeal from './pages/LogMeal'
import Settings from './pages/Settings'

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="/log" element={<LogMeal />} />
        <Route path="/analytics" element={<Analytics />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}
