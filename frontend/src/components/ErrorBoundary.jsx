import React from 'react'

/**
 * Without this, a render error blanks the whole page and the only clue is in
 * the browser console. Showing the message on screen keeps a crash diagnosable.
 */
export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { error: null, info: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, info) {
    this.setState({ info })
    // eslint-disable-next-line no-console
    console.error('Render error:', error, info)
  }

  render() {
    if (!this.state.error) return this.props.children

    return (
      <div style={{ padding: 24 }}>
        <div className="alert alert-bad" data-testid="render-error">
          <strong>Ошибка интерфейса / Interface error</strong>
          <div style={{ marginTop: 8, fontFamily: 'monospace', fontSize: 12.5 }}>
            {String(this.state.error?.message || this.state.error)}
          </div>
        </div>
        {this.state.info?.componentStack && (
          <pre style={{ fontSize: 11, background: '#f6f8fa', padding: 12,
                        borderRadius: 6, overflowX: 'auto' }}>
            {this.state.info.componentStack}
          </pre>
        )}
        <button className="btn" onClick={() => this.setState({ error: null, info: null })}>
          Retry
        </button>
      </div>
    )
  }
}
