import { Component, type ErrorInfo, type ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  error: Error | null
}

/**
 * Root error boundary — a render crash anywhere in the tree shows a reload
 * prompt instead of a permanently blank page.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error:', error, info.componentStack)
  }

  render() {
    if (!this.state.error) {
      return this.props.children
    }
    return (
      <div
        className="min-h-screen flex flex-col items-center justify-center gap-4 px-6 text-center"
        style={{ background: 'var(--bg-primary)', color: 'var(--text-primary)' }}
      >
        <h1 className="text-xl font-bold">Something went wrong</h1>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          The app hit an unexpected error. Reloading usually fixes it.
        </p>
        <button
          onClick={() => window.location.reload()}
          className="btn btn-primary px-4 py-2 rounded-lg text-sm"
        >
          Reload
        </button>
      </div>
    )
  }
}
