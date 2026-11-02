import React, { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { api, errorMessage } from '../api'
import { useI18n } from '../i18n'
import { ru } from '../i18n/ru'
import { kk } from '../i18n/kk'
import QueryResult from '../components/QueryResult'
import ChatReportCard from '../components/ChatReportCard'
import Icon from '../components/Icon'

const assistantModels = {
  'qwen3:1.7b-q4_K_M': { name: 'Qwen3 1.7B', label: 'assistant.modelSmall' },
  'qwen3:4b-instruct-2507-q4_K_M': { name: 'Qwen3 4B', label: 'assistant.modelLarge', hint: 'assistant.modelLargeHint' },
  'qwen3:14b-q4_K_M': { name: 'Qwen3 14B', label: 'assistant.modelAdvanced', hint: 'assistant.modelAdvancedHint' },
}
const active = row => ['queued', 'running'].includes(row.status)
const mergeRows = (previous, rows) => [...new Map([...previous, ...rows].map(row => [row.id, row])).values()]
  .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id.localeCompare(a.id))
const localDate = (value, lang, short = false) => new Date(/(?:Z|[+-]\d\d:\d\d)$/.test(value) ? value : `${value}Z`)
  .toLocaleString(lang === 'kk' ? 'kk-KZ' : 'ru-RU', short ? { day: '2-digit', month: '2-digit' } : { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
const localize = (value, lang) => typeof value === 'object' ? value?.[lang] || value?.ru || ''
  : String(value || '').split(' / ')[lang === 'kk' ? 1 : 0] || String(value || '')
const queryKey = row => JSON.stringify([row.plan?.definition, row.plan?.group_by ?? null])

export default function AssistantPage({ onActiveCount }) {
  const { t, lang } = useI18n()
  const [status, setStatus] = useState(null)
  const [model, setModel] = useState('qwen3:1.7b-q4_K_M')
  const [conversations, setConversations] = useState([])
  const [conversationTotal, setConversationTotal] = useState(0)
  const [loadingConversations, setLoadingConversations] = useState(false)
  const [conversation, setConversation] = useState('new')
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)
  const [history, setHistory] = useState([])
  const [total, setTotal] = useState(0)
  const [activeCount, setActiveCount] = useState(0)
  const [historyError, setHistoryError] = useState(false)
  const [loadingHistory, setLoadingHistory] = useState(false)
  const [error, setError] = useState(null)
  const [queryResults, setQueryResults] = useState({})
  const [cancelling, setCancelling] = useState(null)
  const [refresh, setRefresh] = useState(0)
  const [unread, setUnread] = useState(false)
  const alive = useRef(true)
  const submission = useRef(null)
  const newConversation = useRef(null)
  const drafts = useRef({})
  const historyCache = useRef({})
  const currentView = useRef(conversation)
  const composer = useRef(text)
  const composerElement = useRef(null)
  const modelChanged = useRef(false)
  const interacted = useRef(false)
  const requestRuns = useRef({})
  const transcript = useRef(null)
  const scrollPositions = useRef({})
  const scrollToLatest = useRef(true)
  const preserveScroll = useRef(null)
  const latestSignature = useRef('')
  const sendLock = useRef(false)
  const conversationBusy = conversation !== 'new' && conversation !== 'history' && history.some(active)
  const title = conversations.find(row => row.id === conversation)?.title
  const prompt = text.trim()
  const deterministicReport = [ru.assistantReport.defaultRequest, kk.assistantReport.defaultRequest].includes(prompt)
  const canSend = !sending && !conversationBusy && activeCount < 3 && prompt.length >= 3
    && (status?.available !== false || deterministicReport)
  currentView.current = conversation
  composer.current = text
  historyCache.current[conversation] = { rows: history, total }

  const fitComposer = () => {
    const node = composerElement.current
    if (!node?.clientWidth) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(128, node.scrollHeight + 2)}px`
  }
  useLayoutEffect(fitComposer, [text])
  useEffect(() => {
    const node = composerElement.current
    let width = 0
    const observer = new ResizeObserver(() => {
      const next = node.clientWidth
      if (next !== width) { width = next; fitComposer() }
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [])

  const change = value => {
    interacted.current = true
    composer.current = value
    drafts.current[currentView.current] = value
    setText(value)
  }
  const chooseConversation = id => {
    if (id === currentView.current) return
    interacted.current = true
    drafts.current[currentView.current] = composer.current
    if (transcript.current) scrollPositions.current[currentView.current] = transcript.current.scrollTop
    currentView.current = id
    const cached = historyCache.current[id]
    scrollToLatest.current = scrollPositions.current[id] === undefined
    preserveScroll.current = null
    latestSignature.current = ''
    setConversation(id); setText(drafts.current[id] || '')
    setHistory(cached?.rows || []); setTotal(cached?.total || 0)
    setHistoryError(false); setLoadingHistory(id !== 'new' && !cached)
    setError(null); setUnread(false)
  }
  const startNew = () => {
    newConversation.current = null
    chooseConversation('new'); change('')
    requestAnimationFrame(() => composerElement.current?.focus())
  }
  const refreshConversations = async (offset = 0) => {
    const { data } = await api.assistantConversations(offset)
    if (alive.current) {
      setConversations(previous => [...new Map([...previous, ...data.data].map(row => [row.id, row])).values()]
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at)))
      setConversationTotal(data.total)
    }
    return data.data
  }
  const refreshStatus = async () => {
    try {
      const { data } = await api.assistantStatus()
      if (!alive.current) return
      setStatus(data)
      if (!modelChanged.current && data.model) setModel(data.model)
    } catch { if (alive.current) setStatus({ available: false }) }
  }
  const moreConversations = async () => {
    setLoadingConversations(true)
    try { await refreshConversations(conversations.length) }
    catch (e) { if (alive.current) setError(errorMessage(e)) }
    finally { if (alive.current) setLoadingConversations(false) }
  }
  useEffect(() => {
    alive.current = true
    refreshStatus()
    refreshConversations().then(rows => {
      if (alive.current && !interacted.current && rows.length) chooseConversation(rows[0].id)
    }).catch(() => { if (alive.current) setHistoryError(true) })
    return () => { alive.current = false; requestRuns.current = {} }
  }, [])
  useEffect(() => {
    let valid = true, timer, idlePolls = 0
    const poll = async () => {
      let pending = false
      try {
        const { data } = await api.assistantHistory(0, conversation === 'new' || conversation === 'history' ? undefined : conversation)
        if (!valid || !alive.current || currentView.current !== conversation) return
        setActiveCount(data.active_count ?? data.data.filter(active).length)
        pending = (data.active_count ?? data.data.filter(active).length) > 0
        if (conversation !== 'new') { setHistory(previous => mergeRows(previous, data.data)); setTotal(data.total) }
        setHistoryError(false)
      } catch { if (valid && alive.current) setHistoryError(true) }
      finally {
        if (valid && alive.current) {
          setLoadingHistory(false)
          idlePolls = pending ? 0 : idlePolls + 1
          timer = setTimeout(poll, pending ? 2500 : Math.min(15000, 5000 * idlePolls))
        }
      }
    }
    poll()
    const wake = () => { if (document.visibilityState === 'visible') setRefresh(value => value + 1) }
    document.addEventListener('visibilitychange', wake)
    return () => { valid = false; clearTimeout(timer); document.removeEventListener('visibilitychange', wake) }
  }, [conversation, refresh])
  useEffect(() => { onActiveCount?.(activeCount) }, [activeCount, onActiveCount])
  useEffect(() => {
    requestRuns.current = {}
    setQueryResults({})
  }, [lang])

  // Preserve reading position when older messages arrive. Follow new answers
  // only while the reader is already near the end of the conversation.
  useLayoutEffect(() => {
    const element = transcript.current
    if (!element) return
    const signature = `${conversation}:${history[0]?.id}:${history[0]?.status}`
    if (preserveScroll.current?.view === conversation) {
      element.scrollTop += element.scrollHeight - preserveScroll.current.height
      preserveScroll.current = null
    } else if (scrollToLatest.current) element.scrollTop = element.scrollHeight
    else if (!latestSignature.current && scrollPositions.current[conversation] !== undefined) element.scrollTop = scrollPositions.current[conversation]
    else if (latestSignature.current && signature !== latestSignature.current) setUnread(true)
    latestSignature.current = signature
  }, [conversation, history])
  useEffect(() => {
    const element = transcript.current
    if (!element || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      if (scrollToLatest.current) element.scrollTop = element.scrollHeight
    })
    observer.observe(element)
    if (element.firstElementChild) observer.observe(element.firstElementChild)
    return () => observer.disconnect()
  }, [])
  const goToLatest = () => {
    scrollToLatest.current = true; setUnread(false)
    if (transcript.current) transcript.current.scrollTop = transcript.current.scrollHeight
  }
  const ensureConversation = async () => {
    if (currentView.current !== 'new' && currentView.current !== 'history') return currentView.current
    if (!newConversation.current) newConversation.current = crypto.randomUUID()
    const { data } = await api.assistantConversationCreate(newConversation.current, composer.current.trim().slice(0, 120) || undefined)
    newConversation.current = null
    if (!alive.current) return null
    setConversations(previous => [data, ...previous.filter(row => row.id !== data.id)])
    const textToKeep = composer.current
    chooseConversation(data.id); change(textToKeep)
    return data.id
  }
  const send = async event => {
    event.preventDefault()
    if (!canSend || sendLock.current) return
    sendLock.current = true; setSending(true); setError(null)
    const original = text
    try {
      const conversationId = await ensureConversation()
      if (!conversationId || !alive.current) return
      const signature = `${conversationId}:${model}:${lang}:${prompt}`
      if (submission.current?.signature !== signature) submission.current = { signature, id: crypto.randomUUID() }
      const { data } = await api.assistantSubmit(prompt, lang, submission.current.id, model, conversationId)
      if (!alive.current) return
      submission.current = null
      if (currentView.current === conversationId) {
        scrollToLatest.current = true
        setHistory(previous => mergeRows(previous, [data])); setTotal(value => value + 1)
        if (composer.current === original) change('')
      }
      setRefresh(value => value + 1)
      refreshConversations().catch(() => {})
    } catch (e) { if (alive.current) setError(errorMessage(e)) }
    finally { sendLock.current = false; if (alive.current) setSending(false) }
  }
  const cancel = async requestId => {
    const view = conversation
    setCancelling(requestId); setError(null)
    try {
      const { data } = await api.assistantCancel(requestId)
      if (alive.current && currentView.current === view) setHistory(previous => mergeRows(previous, [data]))
      if (alive.current) setRefresh(value => value + 1)
    } catch (e) { if (alive.current && currentView.current === view) setError(errorMessage(e)) }
    finally { if (alive.current) setCancelling(null) }
  }
  const more = async () => {
    const view = conversation
    setLoadingHistory(true)
    try {
      const { data } = await api.assistantHistory(history.length, view === 'history' ? undefined : view)
      if (alive.current && currentView.current === view) {
        preserveScroll.current = { view, height: transcript.current?.scrollHeight || 0 }
        setHistory(previous => mergeRows(previous, data.data)); setTotal(data.total)
      }
    } catch (e) { if (alive.current && currentView.current === view) setError(errorMessage(e)) }
    finally { if (alive.current && currentView.current === view) setLoadingHistory(false) }
  }
  const runQuery = async (row, reveal = false) => {
    const token = Symbol(row.id), key = queryKey(row)
    requestRuns.current[row.id] = token
    setQueryResults(previous => ({ ...previous, [row.id]: {
      ...(previous[row.id]?.key === key ? previous[row.id] : {}), loading: true, error: null, key,
    } }))
    const current = () => alive.current && requestRuns.current[row.id] === token
    try {
      const { data } = await api.analyticsPreview(row.plan.definition, row.plan.group_by, reveal, lang)
      if (current()) setQueryResults(previous => ({ ...previous, [row.id]: { data, reveal, key, loading: false, open: true } }))
    } catch (e) {
      if (current()) setQueryResults(previous => ({ ...previous, [row.id]: { ...previous[row.id], loading: false, error: errorMessage(e) } }))
    }
  }
  const toggleResult = row => {
    const answer = queryResults[row.id]
    if (!answer?.data || answer.key !== queryKey(row)) runQuery(row)
    else setQueryResults(previous => ({ ...previous, [row.id]: { ...answer, open: !answer.open } }))
  }
  const modelLabel = value => assistantModels[value] ? t(assistantModels[value].label) : value
  const selectedModel = assistantModels[model]

  return <section className="assistant-chat" aria-labelledby="assistant-chat-title">
    <aside className="chat-sidebar" aria-label={t('assistantChat.history')}>
      <div className="chat-sidebar-header"><h2>{t('assistantChat.history')}</h2><button className="btn" onClick={startNew} disabled={sending}><span aria-hidden="true">＋</span>{t('assistantChat.newChat')}</button></div>
      <nav className="chat-conversations" aria-label={t('assistantChat.dialogues')}>
        {conversations.map(row => <button key={row.id} className={`chat-conversation ${conversation === row.id ? 'is-selected' : ''}`} disabled={sending}
          aria-current={conversation === row.id ? 'true' : undefined} onClick={() => chooseConversation(row.id)}>
          <strong>{row.title || t('assistantConversation.untitled')}</strong><span className="chat-conversation-meta">{localDate(row.updated_at, lang, true)}</span>
        </button>)}
        {!conversations.length && <p className="chat-sidebar-empty">{t('assistantChat.noHistory')}</p>}
        {conversations.length < conversationTotal && <button className="btn btn-ghost btn-sm" disabled={loadingConversations || sending} onClick={moreConversations}>{loadingConversations ? t('common.loading') : t('assistantConversation.moreDialogues')}</button>}
      </nav>
      <div className="chat-sidebar-footer"><button className={`chat-history-link ${conversation === 'history' ? 'is-selected' : ''}`} disabled={sending} onClick={() => chooseConversation('history')}><Icon name="audit" size={16} />{t('assistantChat.allHistory')}</button><span><Icon name="shield" size={14} />{t('assistantChat.local')}</span></div>
    </aside>
    <div className="chat-main">
      <header className="chat-toolbar"><div className="chat-title"><h1 id="assistant-chat-title">{t('assistant.nav')}</h1><p>{conversation === 'history' ? t('assistantChat.allHistory') : title || t('assistantChat.newChat')}</p></div>
        <div className="chat-model"><label className="sr-only" htmlFor="assistant-model">{t('assistant.model')}</label><select id="assistant-model" value={model} title={selectedModel?.hint ? t(selectedModel.hint) : modelLabel(model)} aria-describedby={selectedModel?.hint ? 'assistant-model-help' : undefined} onChange={e => { modelChanged.current = true; setModel(e.target.value) }}>
          {(status?.models?.length ? [...new Set([...status.models, model])] : [model]).map(value => <option key={value} value={value}>{modelLabel(value)}</option>)}
        </select>{selectedModel?.hint && <span id="assistant-model-help" className="sr-only">{t(selectedModel.hint)}</span>}</div>
      </header>
      <div className="chat-transcript" ref={transcript} role="log" aria-label={t('assistantChat.messages')} aria-live="polite" aria-relevant="additions text"
        onScroll={() => { const node = transcript.current; if (!node.clientHeight) return; scrollToLatest.current = node.scrollHeight - node.scrollTop - node.clientHeight < 80; if (scrollToLatest.current) setUnread(false) }}>
        <div className="chat-transcript-content">
          {history.length < total && <button className="btn btn-ghost btn-sm chat-load-more" disabled={loadingHistory} onClick={more}>{loadingHistory ? t('common.loading') : t('assistant.more')}</button>}
          {!history.length && <div className="chat-empty"><Icon name="assistant" size={32} /><h2>{t(loadingHistory ? 'common.loading' : 'assistantChat.emptyTitle')}</h2>{!loadingHistory && <p>{t('assistantChat.emptyHint')}</p>}</div>}
          {[...history].reverse().map(row => {
            const plan = row.plan, report = plan?.kind === 'report' || row.kind === 'report'
            const answer = queryResults[row.id], hasResult = answer?.data && answer.key === queryKey(row)
            return <article className="chat-turn" key={row.id}>
              <div className="chat-message chat-user"><div className="chat-message-meta"><strong>{t('assistantChat.you')}</strong><time>{localDate(row.created_at, lang)}</time></div><p className="chat-message-body">{row.prompt}</p>
                {conversation === 'history' && row.conversation_id && <button className="chat-open-dialogue" disabled={sending} onClick={() => chooseConversation(row.conversation_id)}>{t('assistantChat.openDialogue')}</button>}
              </div>
              <div className="chat-message chat-agent"><div className="chat-message-meta"><strong><Icon name="assistant" size={15} />{t('assistant.nav')}</strong><span>{assistantModels[row.model]?.name || row.model}</span></div>
                {active(row) && <div className="chat-pending" role="status"><span className="chat-pending-dot" />{t(`assistant.states.${row.status}`)}<button className="btn btn-ghost btn-sm" disabled={cancelling === row.id} onClick={() => cancel(row.id)}>{t('assistant.cancel')}</button><small>{t('assistant.background')}</small></div>}
                {row.status === 'error' && <p className="chat-inline-error">{t(row.error_code === 'interrupted' ? 'assistant.interrupted' : 'assistantChat.failed')}</p>}
                {row.status === 'cancelled' && <p className="chat-message-body">{t('assistant.cancelledHint')}</p>}
                {plan?.status === 'clarify' && <p className="chat-message-body">{plan.summaries?.[lang] || localize(plan.message || plan.summary, lang) || t('assistant.clarifyHint')}</p>}
                {!!plan?.warnings?.length && <ul className="chat-warnings">{plan.warnings.map((warning, i) => <li key={i}>{localize(warning, lang)}</li>)}</ul>}
                {row.status === 'ready' && plan?.status === 'ready' && report && <ChatReportCard request={row} />}
                {row.status === 'ready' && plan?.status === 'ready' && !report && plan.definition && <>
                  <p className="chat-message-body">{plan.summaries?.[lang] || localize(plan.summary, lang) || t('assistantChat.queryReady')}</p>
                  <div className="chat-message-actions"><button className="btn btn-ghost btn-sm" disabled={answer?.loading} onClick={() => toggleResult(row)} aria-expanded={!!(hasResult && answer.open)}>{answer?.loading ? t('analytics.running') : t(hasResult && answer.open ? 'assistantChat.hideResults' : 'assistantChat.showResults')}</button>
                    {hasResult && answer.open && <button className="btn btn-ghost btn-sm" disabled={answer.loading} onClick={() => runQuery(row, answer.reveal)}>{t('assistantChat.refreshResults')}</button>}
                  </div>
                  {answer?.error && <p className="chat-inline-error" role="alert">{answer.error}</p>}
                  {hasResult && answer.open && <div className="chat-results"><QueryResult result={{ ...answer.data, summary: null }} reveal={answer.reveal} onToggleReveal={() => !answer.loading && runQuery(row, !answer.reveal)} /></div>}
                </>}
                {['error', 'cancelled'].includes(row.status) && <button className="btn btn-ghost btn-sm" onClick={() => { change(row.prompt); composerElement.current?.focus() }}>{t('assistantChat.retryMessage')}</button>}
              </div>
            </article>
          })}
        </div>
      </div>
      {unread && <button className="chat-unread" onClick={goToLatest}>↓ {t('assistantChat.latest')}</button>}
      <form className="chat-composer" onSubmit={send}>
        {historyError && <p className="chat-inline-error" role="status">{t('assistant.historyError')}</p>}
        {error && <p className="chat-inline-error" role="alert">{error}</p>}
        {status?.available === false && <p className="chat-composer-hint">{t('assistant.unavailable')}. <button type="button" className="chat-text-button" onClick={refreshStatus}>{t('errors.retry')}</button></p>}
        <label className="sr-only" htmlFor="assistant-question">{t('assistantChat.message')}</label>
        <div className="chat-composer-row"><textarea id="assistant-question" ref={composerElement} className="chat-composer-input" value={text} onChange={e => change(e.target.value)} rows={1} maxLength={2000}
          placeholder={t('assistantChat.placeholder')} disabled={sending}
          onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(e) } }} />
          <button className="btn chat-send" disabled={!canSend} type="submit" aria-label={sending ? t('common.loading') : t('assistantConversation.send')}><span>{sending ? t('common.loading') : t('assistantConversation.send')}</span><Icon name="arrow" size={17} /></button>
        </div>
        <div className="chat-composer-footer"><p className="chat-composer-hint">{t(conversationBusy ? 'assistantChat.working' : activeCount >= 3 ? 'assistantConversation.queueLimit' : conversation === 'history' ? 'assistantConversation.historyComposer' : 'assistantChat.sendHint')}</p>
          <span className="chat-character-count">{text.length}/2000</span>
        </div>
      </form>
    </div>
  </section>
}
