import React from 'react'
import { useI18n } from '../i18n'
import Icon from './Icon'
import './demoNotice.css'

export function DemoBanner() {
  const { t } = useI18n()
  return <aside className="demo-banner" aria-label={t('renderDemo.label')}>
    <strong>{t('renderDemo.label')}</strong><span>{t('renderDemo.notice')}</span>
  </aside>
}

export function DemoAssistant() {
  const { t } = useI18n()
  return <section className="card demo-assistant" aria-labelledby="demo-assistant-title">
    <div className="demo-assistant-mark"><Icon name="assistant" /></div>
    <div><h1 id="demo-assistant-title">{t('assistant.nav')}</h1>
      <p>{t('renderDemo.assistant')}</p></div>
  </section>
}
