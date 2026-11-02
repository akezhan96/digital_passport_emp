import test from 'node:test'
import assert from 'node:assert/strict'
import { evaluationPayload, hasApplicableSources, hasDossierSource, methodologySections, orderedCriteria, moveItem,
  newSource, sourceOptions, sourceLabel } from '../src/candidateSources.js'
import { candidateDictionaries } from '../src/i18n/candidateMethodology.js'
import { renameMethodologyItem, saveRenamedVersion } from '../src/methodologyEditing.js'

test('custom sections follow saved order and an empty draft remains empty', () => {
  assert.deepEqual(methodologySections({ sections: [] }), [])
  const method = { sections: [{ key: 'sport', position: 20 }, { key: 'work', position: 10 }] }
  assert.deepEqual(methodologySections(method).map(s => s.key), ['work', 'sport'])
  assert.equal(method.sections[0].key, 'sport')
})

test('section and indicator reorder preserve stable score keys and leave source data intact', () => {
  const method = { sections: [{ key: 'sport', position: 0 }, { key: 'work', position: 1 }], criteria: [
    { position: 400, section_key: 'work', display_order: 0 },
    { position: 3, section_key: 'sport', display_order: 20 },
    { position: 780, section_key: 'sport', display_order: 10 },
  ] }
  assert.deepEqual(orderedCriteria(method).map(c => c.position), [780, 3, 400])
  assert.deepEqual(orderedCriteria(method, 'sport').map(c => c.position), [780, 3])
  assert.deepEqual(method.criteria.map(c => c.position), [400, 3, 780])
  assert.deepEqual(moveItem(method.criteria, 0, -1), method.criteria)
  assert.deepEqual(moveItem(method.criteria, 2, 1), method.criteria)
})

test('saved evaluation payload excludes calculated, disabled and non-applicable scores, keeps explicit zero', () => {
  const data = { methodology: { id: 12, criteria: [
    { position: 3, enabled: true, block: 'general' },
    { position: 55, enabled: true, block: 'general', source: { kind: 'dossier_field', field_id: 4 } },
    { position: 80, enabled: false, block: 'general' },
    { position: 99, enabled: true, block: 'technical' },
    { position: 102, enabled: true, block: 'psychological' },
  ] }, revision: 2 }
  assert.deepEqual(evaluationPayload(data, { 3: '0', 55: '15', 80: '20', 99: '5', 102: '' }, false, 'Doc'), {
    methodology_id: 12, expected_revision: 2, technical_profile: false, note: 'Doc', scores: [{ position: 3, points: '0' }],
  })
  assert.equal(hasApplicableSources(data.methodology.criteria, false), true)
  assert.equal(hasApplicableSources([{ enabled: true, block: 'technical', source: { kind: 'dossier_fact' } }], false), false)
})

test('boolean and numeric source rules retain typed false and zero values', () => {
  const catalog = { fields: [
    { id: 7, field_type: 'boolean', options: [{ value: false, name_ru: 'Нет', name_kk: 'Жоқ' }] },
    { id: 8, field_type: 'number', options: [] },
  ] }
  assert.deepEqual(newSource('field:7', catalog, 10).rules, [{ operator: 'eq', value: false, points: 10 }])
  assert.deepEqual(newSource('field:8', catalog, 15).rules, [{ operator: 'gte', value: 0, points: 15 }])
  assert.equal(newSource('manual', catalog, 10), null)
  assert.equal(newSource('field:999', catalog, 10), null)
})

test('language source options stay within the selected scale', () => {
  const definition = { code: 'language_level', field_type: 'number', arguments: [{ value: 8 }],
    scales: [{ value: 2 }], options: [{ value: 1, scale_id: 1 }, { value: 2, scale_id: 2 }] }
  const source = newSource('fact:language_level', { facts: [definition] }, 20)
  assert.equal(source.argument, 8)
  assert.equal(source.scale_id, 2)
  assert.equal(source.rules[0].value, 2)
  assert.deepEqual(sourceOptions({ ...source, scale_id: 1 }, definition), [{ value: 1, scale_id: 1 }])
})

test('source labels and constructor dictionaries support Russian and Kazakh equally', () => {
  assert.equal(sourceLabel({ value: 'A', name_ru: 'Есть', name_kk: 'Бар' }, 'kk'), 'Бар')
  assert.equal(sourceLabel({ label_ru: 'Источник', label_kk: 'Дереккөз' }, 'kk'), 'Дереккөз')
  assert.deepEqual(Object.keys(candidateDictionaries.ru).sort(), Object.keys(candidateDictionaries.kk).sort())
  assert.ok(Object.values(candidateDictionaries.ru).every(value => typeof value === 'string' && value.trim()))
  assert.ok(Object.values(candidateDictionaries.kk).every(value => typeof value === 'string' && value.trim()))
})

const renameFixture = () => ({ id: 4, version: 3, status: 'active', revision: 2,
  name_ru: 'Оценка', name_kk: 'Бағалау',
  sections: [{ key: 'work', kind: 'general', position: 0, name_ru: 'Общие', name_kk: 'Жалпы' }],
  criteria: [{ id: 90, position: 300, section_key: 'work', block: 'general', display_order: 0,
    name_ru: 'Проект', name_kk: 'Жоба', max_points: 15, enabled: true,
    source: { kind: 'dossier_field', field_id: 8, rules: [{ operator: 'gte', value: 0, points: 15 }] } }],
})

test('section renaming changes translations without changing score keys, membership or the original version', () => {
  const method = renameFixture(), before = structuredClone(method)
  const result = renameMethodologyItem(method, { kind: 'section', sectionKey: 'work' }, { name_ru: ' Опыт ', name_kk: ' Тәжірибе ' })
  assert.equal(result.sections[0].name_ru, 'Опыт')
  assert.equal(result.sections[0].name_kk, 'Тәжірибе')
  assert.equal(result.sections[0].key, 'work')
  assert.equal(result.sections[0].kind, 'general')
  assert.deepEqual(result.criteria, before.criteria)
  assert.deepEqual(method, before)
})

test('criterion renaming uses its stable position after cloning and preserves every scoring rule', () => {
  const cloned = renameFixture()
  cloned.id = 7; cloned.criteria[0].id = 501
  const result = renameMethodologyItem(cloned, { kind: 'criterion', position: 300 }, { name_ru: 'Опыт проекта', name_kk: 'Жоба тәжірибесі' })
  assert.deepEqual(result.criteria[0], { ...cloned.criteria[0], name_ru: 'Опыт проекта', name_kk: 'Жоба тәжірибесі' })
  assert.equal(cloned.criteria[0].name_ru, 'Проект')
  assert.equal(renameMethodologyItem(cloned, { kind: 'criterion', position: 301 }, { name_ru: 'Имя', name_kk: 'Атау' }), null)
  assert.equal(renameMethodologyItem(cloned, { kind: 'section', sectionKey: 'work' }, { name_ru: ' ', name_kk: 'Атау' }), null)
})

test('renaming a published version saves only its new draft, without publishing or modifying history', async () => {
  const method = renameFixture(), draft = { ...structuredClone(method), id: 7, status: 'draft', version: 4, revision: 1 }
  draft.criteria[0].id = 501
  const calls = [], remembered = []
  const api = {
    clone: async id => { calls.push(['clone', id]); return { data: draft } },
    update: async (id, payload) => { calls.push(['update', id, payload]); return { data: { ...draft, ...payload, revision: 2 } } },
  }
  const result = await saveRenamedVersion(api, method, { kind: 'criterion', position: 300 },
    { name_ru: 'Опыт', name_kk: 'Тәжірибе' }, null, item => remembered.push(item))
  assert.deepEqual(calls.map(call => call.slice(0, 2)), [['clone', 4], ['update', 7]])
  assert.equal(calls[1][2].expected_revision, 1)
  assert.equal(calls[1][2].criteria[0].id, 501)
  assert.equal(result.status, 'draft')
  assert.equal(result.criteria[0].name_ru, 'Опыт')
  assert.equal(method.criteria[0].name_ru, 'Проект')
  assert.equal(remembered[0].id, 7)
})

test('retry after a failed rename reuses and refreshes its draft instead of creating duplicate versions', async () => {
  const method = renameFixture(), draft = { ...structuredClone(method), id: 7, status: 'draft', revision: 1 }
  let pending = null, clones = 0, attempts = 0, reads = 0
  const api = {
    clone: async () => { clones++; return { data: draft } },
    model: async id => { reads++; assert.equal(id, 7); return { data: { ...draft, revision: 3,
      criteria: draft.criteria.map(item => ({ ...item, max_points: 20 })) } } },
    update: async (id, payload) => {
      attempts++; if (attempts === 1) throw new Error('Temporary transport error')
      assert.equal(id, 7); assert.equal(payload.expected_revision, 3)
      assert.equal(payload.criteria[0].max_points, 20)
      return { data: { ...draft, ...payload, revision: 4 } }
    },
  }
  const target = { kind: 'section', sectionKey: 'work' }, names = { name_ru: 'Опыт', name_kk: 'Тәжірибе' }
  await assert.rejects(saveRenamedVersion(api, method, target, names, pending, item => { pending = item }), /Temporary transport error/)
  const result = await saveRenamedVersion(api, method, target, names, pending, item => { pending = item })
  assert.equal(clones, 1); assert.equal(reads, 1); assert.equal(attempts, 2)
  assert.equal(result.sections[0].name_ru, 'Опыт')
  assert.equal(result.criteria[0].max_points, 20)
})

test('typed custom tab rules preserve identity, explicit dates and source ownership', () => {
  const catalog = {tab_fields: [
    {id:7, field_type:'text', name_ru:'Организация', section_ru:'Сертификаты'},
    {id:8, field_type:'date', name_ru:'Срок действия', section_ru:'Сертификаты'},
  ]}
  assert.equal(sourceLabel(catalog.tab_fields[1], 'ru'), 'Сертификаты · Срок действия')
  assert.equal(sourceLabel({name_kk:'Өріс', section_kk:'Құжаттар'}, 'kk'), 'Құжаттар · Өріс')
  assert.equal(sourceLabel({name_ru:'Старое поле'}, 'ru'), 'Старое поле')
  const expiry = newSource('tab:8', catalog, 10)
  assert.deepEqual(expiry, {kind:'tab_field', field_id:8, rules:[{operator:'gte', value:'today',points:10}]})
  assert.deepEqual(newSource('tab:7', catalog, 5).rules,[{operator:'present',value:'',points:5}])
  assert.equal(newSource('tab:99',catalog,5), null)
  assert.equal(hasDossierSource({source:expiry}),true)
  const data={methodology:{id:7,criteria:[{enabled:true,position:3,block:'general',source:expiry}]},revision:1}
  assert.deepEqual(evaluationPayload(data,{3:300},false,'').scores,[])
})

