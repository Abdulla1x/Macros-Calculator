import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { registerSW } from 'virtual:pwa-register'
import './index.css'
import App from './App.tsx'
import { AuthProvider } from './auth/AuthContext'
import ErrorBoundary from './components/ErrorBoundary'

// Runs at module scope, before render, where no error boundary can reach it.
// Service worker registration is an enhancement — offline caching and the
// install prompt — and the app is fully usable without it, so a browser that
// refuses it must not take the page down on the way in.
try {
  registerSW()
} catch (err) {
  console.error('Service worker registration failed:', err)
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {/* Outside AuthProvider deliberately: the provider reads the stored token
        during its first render, which is exactly where the white-screen crash
        on a storage-blocked browser came from. A boundary inside it would
        never have caught that. */}
    <ErrorBoundary>
      {/* The router itself is created in App.tsx (a data router, for
          useBlocker). AuthProvider sits outside it: it uses no router hooks,
          and RequireAuth inside the tree does the redirecting. */}
      <AuthProvider>
        <App />
      </AuthProvider>
    </ErrorBoundary>
  </StrictMode>,
)
