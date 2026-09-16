import { Component, type ErrorInfo, type ReactNode } from 'react'
import { RefreshCw, RotateCcw } from 'lucide-react'
import { Button } from './ui'

interface Props {
  children: ReactNode
  /** changing it (e.g. navigating) clears a previous crash */
  resetKey?: string
}

interface State {
  error: Error | null
}

/** Keeps a rendering bug in one view from blanking the whole studio. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Dubby UI error:', error, info.componentStack)
  }

  componentDidUpdate(prev: Props) {
    if (prev.resetKey !== this.props.resetKey && this.state.error) this.setState({ error: null })
  }

  render() {
    const { error } = this.state
    if (!error) return this.props.children
    return (
      <div className="mx-auto max-w-xl px-4 py-16">
        <div className="scale-in rounded-2xl border border-line-strong bg-panel p-6 backdrop-blur-xl">
          <div className="text-3xl">🐨</div>
          <h2 className="mt-3 text-lg font-semibold">This view hit an unexpected error</h2>
          <p className="mt-1 text-sm text-neutral-400">Your project is safe — everything is saved by the studio. Try again, or reload the page.</p>
          <pre className="mt-4 max-h-40 overflow-auto whitespace-pre-wrap rounded-xl border border-line bg-black/40 p-3 font-mono text-[11px] text-neutral-400">{error.message}</pre>
          <div className="mt-5 flex flex-wrap gap-2">
            <Button variant="primary" icon={<RotateCcw className="size-4" />} onClick={() => this.setState({ error: null })}>
              Try again
            </Button>
            <Button icon={<RefreshCw className="size-4" />} onClick={() => window.location.reload()}>
              Reload page
            </Button>
          </div>
        </div>
      </div>
    )
  }
}
