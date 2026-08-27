import { Component, type ErrorInfo, type ReactNode } from 'react'
import Card from './ui/Card'

/** The last thing between a thrown render error and a blank white page.
 *
 * React unmounts the whole tree when a render throws and nothing catches it,
 * which leaves the user looking at an empty document with no indication that
 * anything happened — not an error, not a reload prompt, nothing to report.
 *
 * This is the only class component in the codebase, and has to be: error
 * boundaries have no hook equivalent. React has not added one, so this is not a
 * style choice that will age out.
 *
 * Placed outside AuthProvider in main.tsx on purpose. The crash it was written
 * for happened *inside* AuthProvider, which reads the stored token during its
 * first render; a boundary nested under the provider would never have seen it.
 */
interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // There is no error-reporting service wired up, so the console is the whole
    // trail. Logging the component stack as well as the error is what makes it
    // usable in a screenshot from someone else's browser.
    console.error('Unhandled render error:', error, info.componentStack)
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div className="flex min-h-screen items-center justify-center bg-slate-950 p-6 text-slate-100">
        <Card pad="lg" className="w-full max-w-md">
          <h1 className="text-lg font-semibold">Something broke on this page</h1>
          <p className="mt-3 text-sm text-slate-300">
            Not your data — that is safe on the server. This is the app failing
            to draw itself, and reloading usually clears it.
          </p>
          <p className="mt-3 text-sm text-slate-300">
            If it keeps happening, one known cause is a browser set to block
            site data. Allowing it for this site, or leaving private browsing,
            fixes that particular case.
          </p>
          <button
            onClick={() => window.location.reload()}
            className="mt-5 w-full rounded-lg bg-amber-500 px-4 py-2 font-semibold text-slate-950 hover:bg-amber-400"
          >
            Reload
          </button>
          {/* The message itself, not a friendly paraphrase: it is the only
              thing that makes a bug report actionable, and hiding it helps
              nobody who is already looking at a broken page. */}
          <p className="mt-4 break-words text-xs text-slate-400">
            {this.state.error.message || String(this.state.error)}
          </p>
        </Card>
      </div>
    )
  }
}
