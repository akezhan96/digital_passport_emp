import React from 'react'
import { useI18n } from '../i18n'
function Failure({ retry }) { const { t } = useI18n(); return <div className="card"><div className="alert alert-bad" role="alert"><strong>{t('errors.title')}</strong><p>{t('errors.hint')}</p></div><button className="btn" onClick={retry}>{t('errors.retry')}</button></div> }
export default class ErrorBoundary extends React.Component {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? <Failure retry={() => this.setState({ failed: false })} /> : this.props.children }
}
