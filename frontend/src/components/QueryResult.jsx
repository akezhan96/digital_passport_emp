import React from 'react'
import { useI18n } from '../i18n'

const methodologyLabels = {
  ru: { title: 'Оценка по методике', version: 'Версия', filled: 'Заполнено',
    partial: 'Без закрытых показателей', preliminary: 'Предварительный итог', noScore: 'Не оценено' },
  kk: { title: 'Әдістеме бойынша баға', version: 'Нұсқа', filled: 'Толтырылды',
    partial: 'Жабық көрсеткіштерсіз', preliminary: 'Алдын ала қорытынды', noScore: 'Бағаланбаған' },
}

function MethodologyResult({ summary, lang }) {
  const labels = methodologyLabels[lang] || methodologyLabels.ru
  if (!summary) return <span className="muted">—</span>
  const number = value => value == null ? '—' : Number(value).toLocaleString(
    lang === 'kk' ? 'kk-KZ' : 'ru-RU', { maximumFractionDigits: 2 })
  return <div style={{ minWidth: 165, fontSize: 12, lineHeight: 1.55 }}
    title={summary[`name_${lang}`] || summary.name_ru || labels.title}>
    <div style={{ whiteSpace: 'nowrap' }}><strong>{number(summary.earned_points)} / {number(summary.max_points)}</strong>
      <span> · {number(summary.percent)}{summary.percent == null ? '' : '%'}</span></div>
    <div className="muted" style={{ fontSize: 11 }}>{labels.version} {summary.version} · {labels.filled} {summary.filled_count}/{summary.applicable_count}</div>
    {summary.earned_points == null ? <div className="muted" style={{ fontSize: 11 }}>{labels.noScore}</div>
      : !summary.complete && <div className="muted" style={{ fontSize: 11 }}>{labels.preliminary}</div>}
    {summary.partial_visibility && <span className="badge badge-warn" style={{ fontSize: 10, marginTop: 3 }}>{labels.partial}</span>}
  </div>
}

/** The answer to any analytics question: a number, a breakdown, and the people. */
export default function QueryResult({ result, reveal, onToggleReveal }) {
  const { t, lang, text } = useI18n()
  if (!result) return null

  const maxCount = result.breakdown?.[0]?.count || 1
  const hasMethodology = result.employees.some(employee => employee.methodology_summary)

  return (
    <>
      <div className="card">
        {result.summary && (
          <div className="muted" style={{ fontSize: 12.5, marginBottom: 10 }}>
            {result.summary}
          </div>
        )}
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 12,
                      flexWrap: 'wrap' }}>
          <div className="stat-value" style={{ fontSize: 34, color: 'var(--accent)' }}>
            {result.count}
          </div>
          <div className="muted">
            {t('analytics.ofTotal')} {result.total} · {result.percent}%
          </div>
        </div>
        <div className="meter" style={{ marginTop: 10 }}>
          <div className="meter-fill" style={{ width: `${result.percent}%` }} />
        </div>
      </div>

      {result.breakdown?.length > 0 && (
        <div className="card flush">
          <div style={{ padding: '11px 14px',
                        borderBottom: '1px solid var(--slate-200)',
                        fontWeight: 620, fontSize: 13 }}>
            {t('analytics.breakdown')}
            {result.group_by_ru && (
              <span className="muted"> · {text(result.group_by_ru)}</span>
            )}
          </div>
          <table>
            <thead><tr>
              <th>{t('analytics.label')}</th>
              <th className="num">{t('analytics.count')}</th>
              <th style={{ width: '45%' }} />
            </tr></thead>
            <tbody>
              {result.breakdown.map((b, i) => (
                <tr key={i}>
                  <td>{text(b[`label_${lang}`] || b.label)}</td>
                  <td className="num"><strong>{b.count}</strong></td>
                  <td>
                    <div className="meter">
                      <div className="meter-fill"
                           style={{ width: `${b.count / maxCount * 100}%` }} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="card flush">
        <div style={{ padding: '11px 14px',
                      borderBottom: '1px solid var(--slate-200)',
                      display: 'flex', justifyContent: 'space-between',
                      alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
          <strong style={{ fontSize: 13 }}>
            {t('analytics.matched')}
            <span className="muted"> ({result.employees.length})</span>
          </strong>
          {onToggleReveal && (
            <button className="btn btn-ghost btn-sm" onClick={onToggleReveal}>
              {reveal ? t('matching.hideNames') : t('matching.revealNames')}
            </button>
          )}
        </div>

        {result.employees.length === 0 ? (
          <div className="empty">{t('common.none')}</div>
        ) : (
          <table>
            <thead><tr>
              <th>{t('employee.fullName')}</th>
              <th>{t('employee.position')}</th>
              <th>{t('employee.orgUnit')}</th>
              {hasMethodology && <th>{(methodologyLabels[lang] || methodologyLabels.ru).title}</th>}
              <th>{t('common.status')}</th>
            </tr></thead>
            <tbody>
              {result.employees.map((e) => (
                <tr key={e.id}>
                  <td><strong>{e.display_name}</strong></td>
                  <td className="muted">{e[`position_${lang}`] || e.position || '—'}</td>
                  <td className="muted">{e[`org_unit_${lang}`] || e.org_unit || '—'}</td>
                  {hasMethodology && <td><MethodologyResult summary={e.methodology_summary} lang={lang} /></td>}
                  <td>
                    <span className={`badge ${e.profile_status === 'verified'
                      ? 'badge-ok' : 'badge-warn'}`}>
                      {t(`employee.status.${e.profile_status}`)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <div className="muted" style={{ fontSize: 11.5, padding: '8px 14px' }}>
          {t('matching.revealHint')}
        </div>
      </div>
    </>
  )
}
