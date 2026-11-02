import React, { useEffect, useState } from 'react'
import { useI18n } from '../i18n'
import { candidateText } from '../i18n/candidateMethodology'
import { criterionSection, hasDossierSource, methodologySections, moveItem, orderedCriteria, sourceDefinition, sourceLabel } from '../candidateSources'
import CandidateSourceEditor from './CandidateSourceEditor'

export default function MethodologyBuilder({ method, locked, busy, sources, onChange, onAddField }) {
  const { lang, pick } = useI18n()
  const copy = candidateText(lang)
  const sections = methodologySections(method)
  const [selected, setSelected] = useState(sections[0]?.key || null)
  const [sourcePosition, setSourcePosition] = useState(null)
  const [search, setSearch] = useState('')
  useEffect(() => { setSelected(methodologySections(method)[0]?.key || null); setSearch(''); setSourcePosition(null) }, [method.id])
  const selectedSection = sections.find(section => section.key === selected) || sections[0]
  const sectionCriteria = orderedCriteria(method, selectedSection?.key)
  const rows = selectedSection ? sectionCriteria.filter(c => `${c.name_ru} ${c.name_kk}`.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())) : []
  const updateSection = (key, value) => onChange({ ...method, sections: sections.map(section => section.key === selectedSection.key ? { ...section, [key]: value } : section),
    ...(key === 'kind' ? { criteria: method.criteria.map(c => criterionSection(c) === selectedSection.key ? { ...c, block: value, ...(value === 'psychological' ? { source: null } : {}) } : c) } : {}) })
  const changeCriterion = (position, key, value) => onChange({ ...method, criteria: method.criteria.map(c => c.position === position ? { ...c, [key]: value } : c) })
  const addSection = () => {
    const section = { key: `section_${globalThis.crypto.randomUUID().replaceAll('-', '').slice(0, 12)}`, name_ru: 'Новый раздел', name_kk: 'Жаңа бөлім', kind: 'general', position: sections.length }
    onChange({ ...method, sections: [...sections, section] }); setSelected(section.key); setSearch('')
  }
  const removeSection = () => {
    if (!window.confirm(`${copy.removeSectionConfirm} «${pick(selectedSection)}» (${sectionCriteria.length})`)) return
    const remaining = sections.filter(section => section.key !== selectedSection.key).map((section, index) => ({ ...section, position: index }))
    onChange({ ...method, sections: remaining, criteria: method.criteria.filter(c => criterionSection(c) !== selectedSection.key) })
    setSelected(remaining[0]?.key || null)
  }
  const moveSection = direction => onChange({ ...method, sections: moveItem(sections, sections.findIndex(section => section.key === selectedSection.key), direction).map((section, position) => ({ ...section, position })) })
  const addCriterion = () => {
    const position = Math.max(2, ...method.criteria.map(c => c.position)) + 1
    onChange({ ...method, criteria: [...method.criteria, { position, section_key: selectedSection.key, block: selectedSection.kind,
      display_order: sectionCriteria.length, name_ru: 'Новый показатель', name_kk: 'Жаңа көрсеткіш', max_points: 5, enabled: true, source: null }] })
    setSearch('')
  }
  const removeCriterion = criterion => {
    if (window.confirm(`${copy.removeCriterionConfirm} «${pick(criterion)}»?`)) onChange({ ...method, criteria: method.criteria.filter(c => c.position !== criterion.position) })
  }
  const moveCriterion = (criterion, direction) => {
    const ordered = moveItem(sectionCriteria, sectionCriteria.findIndex(c => c.position === criterion.position), direction)
    const ranks = Object.fromEntries(ordered.map((c, index) => [c.position, index]))
    onChange({ ...method, criteria: method.criteria.map(c => ranks[c.position] === undefined ? c : { ...c, display_order: ranks[c.position] }) })
  }
  return <div className="methodology-builder">
    <aside className="methodology-sections" aria-label={copy.sections}>
      <div className="methodology-section-heading"><strong>{copy.sections}</strong><span className="muted">{sections.length}</span></div>
      <div className="methodology-section-list">{sections.map(section => <button key={section.key} type="button" className={selectedSection?.key === section.key ? 'active' : ''} onClick={() => { setSelected(section.key); setSearch(''); setSourcePosition(null) }} aria-pressed={selectedSection?.key === section.key}>
        <span>{pick(section)}</span><small>{method.criteria.filter(c => criterionSection(c) === section.key).length}</small>
      </button>)}</div>
      {!locked && <button type="button" className="btn btn-ghost btn-sm" disabled={busy || sections.length >= 50} onClick={addSection}>+ {copy.addSection}</button>}
    </aside>
    <div className="methodology-criteria">
      {!selectedSection ? <div className="methodology-empty"><h3>{copy.noSections}</h3>{!locked && <button className="btn" type="button" disabled={busy} onClick={addSection}>{copy.addSection}</button>}</div> : <>
        <div className="candidate-toolbar methodology-section-title"><strong>{pick(selectedSection)}</strong>
          {!locked && <div className="candidate-row-actions"><button type="button" className="btn btn-ghost btn-sm" aria-label={copy.moveSectionUp} disabled={busy || sections[0].key === selectedSection.key} onClick={() => moveSection(-1)}>↑</button>
            <button type="button" className="btn btn-ghost btn-sm" aria-label={copy.moveSectionDown} disabled={busy || sections.at(-1).key === selectedSection.key} onClick={() => moveSection(1)}>↓</button>
            <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={removeSection}>{copy.removeSection}</button></div>}
        </div>
        {!locked && <div className="methodology-section-edit"><label>{copy.sectionNameRu}<input required maxLength={200} value={selectedSection.name_ru} disabled={busy} onChange={e => updateSection('name_ru', e.target.value)} /></label>
          <label>{copy.sectionNameKk}<input required maxLength={200} value={selectedSection.name_kk} disabled={busy} onChange={e => updateSection('name_kk', e.target.value)} /></label>
          <label>{copy.sectionKind}<select value={selectedSection.kind} disabled={busy} onChange={e => {
            if (e.target.value === 'psychological' && sectionCriteria.some(hasDossierSource) && !window.confirm(copy.privateSectionConfirm)) return
            updateSection('kind', e.target.value)
          }}>{['general', 'technical', 'psychological'].map(kind => <option key={kind} value={kind}>{copy[`sectionKind_${kind}`]}</option>)}</select></label>
        </div>}
        <div className="candidate-toolbar methodology-criteria-toolbar"><input type="search" value={search} aria-label={copy.findCriterion} placeholder={copy.findCriterion} onChange={e => setSearch(e.target.value)} />
          {!locked && <button type="button" className="btn btn-ghost btn-sm" disabled={busy || method.criteria.length >= 500} onClick={addCriterion}>+ {copy.addCriterion}</button>}</div>
        {!rows.length ? <div className="methodology-empty"><p>{search ? copy.noCriteriaFound : copy.noCriteria}</p>{!locked && !search && <button type="button" className="btn" disabled={busy} onClick={addCriterion}>{copy.addCriterion}</button>}</div>
          : <div className="candidate-scroll"><table className="methodology-criterion-table"><thead><tr><th>{copy.name}</th><th>{copy.source}</th><th>{copy.maximum}</th><th>{copy.enabled}</th>{!locked && <th>{copy.actions}</th>}</tr></thead><tbody>
            {rows.map(criterion => <React.Fragment key={criterion.position}><tr>
              <td>{locked ? pick(criterion) : <div className="methodology-criterion-names">{['ru', 'kk'].map(language => <label key={language}><small>{language === 'ru' ? 'Русский' : 'Қазақша'}</small><input required maxLength={200} value={criterion[`name_${language}`]} disabled={busy} aria-label={`${language === 'ru' ? copy.nameRu : copy.nameKk}: ${pick(criterion)}`} onChange={e => changeCriterion(criterion.position, `name_${language}`, e.target.value)} /></label>)}</div>}</td>
              <td className="candidate-source-cell">{selectedSection.kind === 'psychological' || (locked && !hasDossierSource(criterion)) ? copy.manual : <button type="button" className="candidate-name-button" disabled={busy || !sources} aria-expanded={sourcePosition === criterion.position} onClick={() => setSourcePosition(old => old === criterion.position ? null : criterion.position)}>
                {hasDossierSource(criterion) ? sourceLabel(sourceDefinition(criterion.source, sources) || criterion.source, lang) || copy.fromDossier : copy.manual}</button>}{criterion.source?.visibility === 'admin' && <small>{copy.privateField}</small>}</td>
              <td>{locked ? Number(criterion.max_points).toLocaleString(lang === 'kk' ? 'kk-KZ' : 'ru-RU') : <input type="number" required min="0.01" max="10000" step="0.01" disabled={busy} aria-label={`${copy.maximum}: ${pick(criterion)}`} value={criterion.max_points} onChange={e => changeCriterion(criterion.position, 'max_points', e.target.value)} />}</td>
              <td><input type="checkbox" checked={criterion.enabled} disabled={locked || busy} aria-label={`${copy.enabled}: ${pick(criterion)}`} onChange={e => changeCriterion(criterion.position, 'enabled', e.target.checked)} /></td>
              {!locked && <td><div className="candidate-row-actions"><button type="button" className="btn btn-ghost btn-sm" disabled={busy || Boolean(search) || sectionCriteria[0].position === criterion.position} aria-label={`${copy.moveUp}: ${pick(criterion)}`} onClick={() => moveCriterion(criterion, -1)}>↑</button>
                <button type="button" className="btn btn-ghost btn-sm" disabled={busy || Boolean(search) || sectionCriteria.at(-1).position === criterion.position} aria-label={`${copy.moveDown}: ${pick(criterion)}`} onClick={() => moveCriterion(criterion, 1)}>↓</button>
                <button type="button" className="btn btn-ghost btn-sm" disabled={busy} aria-label={`${copy.remove}: ${pick(criterion)}`} onClick={() => removeCriterion(criterion)}>×</button></div></td>}
            </tr>{sourcePosition === criterion.position && selectedSection.kind !== 'psychological' && <tr className="candidate-source-detail"><td colSpan={locked ? 4 : 5}><CandidateSourceEditor criterion={criterion} catalog={sources} disabled={locked || busy} onChange={source => changeCriterion(criterion.position, 'source', source)} />
              {!locked && <button type="button" className="btn btn-ghost btn-sm" disabled={busy} onClick={onAddField}>{copy.addField}</button>}</td></tr>}</React.Fragment>)}
          </tbody></table></div>}
      </>}
    </div>
  </div>
}
