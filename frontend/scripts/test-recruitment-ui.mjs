import test from 'node:test'
import assert from 'node:assert/strict'
import { recruitmentExplanation, recruitmentReason, resultScore, recruitmentQuery, recruitmentLink } from '../src/recruitment.js'
import { recruitmentText } from '../src/i18n/recruitment.js'

test('review explanations accept frozen bilingual objects without passing objects into React', () => {
  const review = { ru: 'Нет полной оценки', kk: 'Толық баға жоқ' }
  assert.equal(recruitmentExplanation(review, 'ru'), 'Нет полной оценки')
  assert.equal(recruitmentExplanation(review, 'kk'), 'Толық баға жоқ')
  assert.equal(recruitmentExplanation({ ru: 'Резерв' }, 'kk'), 'Резерв')
  for (const value of [null, undefined, {}, [], { detail: 'incomplete snapshot' }, { ru: {} }]) {
    assert.equal(typeof recruitmentExplanation(value), 'string')
  }
  assert.equal(recruitmentExplanation('not assessed', 'ru'), 'Не оценено')
})

test('frozen points and percentages survive zero values and missing assessments', () => {
  assert.deepEqual(resultScore({ score: 0, methodology_summary: { earned_points: 0, max_points: 100, percent: 0 } }), { percent: '0%', points: '0 / 100' })
  assert.deepEqual(resultScore({ score: 80, methodology_summary: { earned_points: 120, max_points: 150, percent: 80 } }), { percent: '80%', points: '120 / 150' })
  assert.deepEqual(resultScore({ score: 80, explanation: { kind: 'candidate_methodology', requirements: [] }, methodology_summary: { earned_points: 120, max_points: 150, percent: 80 } }), { percent: '80%', points: '120 / 150' })
  assert.deepEqual(resultScore({ score: 0, readiness_code: 'not_assessed', methodology_summary: { earned_points: null, max_points: 100, percent: null } }), { percent: '—', points: null })
  assert.deepEqual(resultScore({ score: 20, methodology_summary: null }), { percent: '20%', points: null })
  assert.deepEqual(resultScore({ score: 55, explanation: { requirements: [] }, methodology_summary: { earned_points: 10, max_points: 20, percent: 50 } }), { percent: '55%', points: null })
  assert.deepEqual(resultScore({ score: NaN, methodology_summary: { earned_points: Infinity, max_points: 10, percent: NaN } }), { percent: '—', points: null })
})

test('review reasons show identical localized requirement and detail only once', () => {
  const detail = { ru: 'Коэффициент ниже порога вакансии', kk: 'Коэффициент бос орын шегінен төмен' }
  assert.equal(recruitmentReason(detail.ru, detail, 'ru'), detail.ru)
  assert.equal(recruitmentReason(detail.kk, detail, 'kk'), detail.kk)
  assert.equal(recruitmentReason('Профиль', { ru: 'Нужна проверка' }), 'Профиль — Нужна проверка')
  assert.equal(recruitmentReason('', detail), detail.ru)
})

test('vacancy and result links retain identity without automatically revealing names', () => {
  const link = recruitmentLink('matching', { run: 59, result: 321, names: undefined })
  assert.equal(link, '#/matching?run=59&result=321')
  assert.deepEqual(recruitmentQuery(link), { vacancy: null, run: 59, result: 321, names: false })
  assert.deepEqual(recruitmentQuery('#/matching?vacancy=3&names=1'), { vacancy: 3, run: null, result: null, names: true })
  assert.deepEqual(recruitmentQuery('#/matching?run=-1&result=999999999999999999&vacancy=abc'), { vacancy: null, run: null, result: null, names: false })
  assert.equal(recruitmentLink('employees', { employee: 7, tab: 'candidate' }), '#/employees?employee=7&tab=candidate')
})

test('every recruitment message has Russian and Kazakh text', () => {
  const ru = recruitmentText('ru'), kk = recruitmentText('kk')
  assert.deepEqual(Object.keys(ru).sort(), Object.keys(kk).sort())
  for (const [key, value] of Object.entries(ru)) {
    assert.ok(value.trim(), key)
    assert.ok(kk[key].trim(), key)
  }
  for (const reason of ['not_selected', 'selection_superseded', 'already_appointed', 'vacancy_closed', 'vacancy_changed', 'employee_inactive', 'forbidden']) assert.ok(ru[reason], reason)
})
