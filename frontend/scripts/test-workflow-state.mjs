import test from 'node:test'
import assert from 'node:assert/strict'
import { formFingerprint } from '../src/formChanges.js'
import { employeeDirectoryTarget } from '../src/appRoute.js'
import { evaluationDisplayState, recruitmentActions } from '../src/workflowUi.js'
import { createUnsavedChangesGuard, CANDIDATE_SCOPE } from '../src/unsavedChanges.js'
import { employeeDirectoryText } from '../src/i18n/employeeDirectory.js'

test('form comparison accepts restored input values without false dirty warnings', () => {
  assert.equal(formFingerprint({ unit: 12, date: null, confirmed: true }), formFingerprint({ confirmed: true, date: '', unit: '12' }))
  assert.equal(formFingerprint({ scores: {} }), formFingerprint({ scores: { 42: '' } }))
  assert.notEqual(formFingerprint({ score: 0 }), formFingerprint({ score: '' }))
  assert.notEqual(formFingerprint({ confirmed: false }), formFingerprint({ confirmed: null }))
  assert.notEqual(formFingerprint({ name: 'А' }), formFingerprint({ name: 'Б' }))
})

test('profile navigation covers child forms while cancelling one form ignores sibling drafts', () => {
  const prompts = []
  const guard = createUnsavedChangesGuard({ confirm: message => { prompts.push(message); return false } })
  const row = `${CANDIDATE_SCOPE}:row-education:2`
  let baseline = formFingerprint({ institution: 'А', reason: '' })
  let current = { institution: 'А', reason: '' }
  const unregister = guard.register(() => ({ dirty: formFingerprint(current) !== baseline, message: 'unsaved row' }), row)
  assert.equal(guard.confirmLeave(CANDIDATE_SCOPE), true)
  current.institution = 'Б'
  assert.equal(guard.confirmLeave(CANDIDATE_SCOPE), false)
  assert.equal(guard.confirmLeave(`${CANDIDATE_SCOPE}:row-education`), false)
  assert.equal(guard.confirmLeave(`${CANDIDATE_SCOPE}:general`), true)
  assert.equal(current.institution, 'Б') // cancelled navigation retains input
  assert.equal(guard.confirmLeave(), false) // failed save must not accept the baseline
  baseline = formFingerprint(current) // only a confirmed save accepts it
  assert.equal(guard.confirmLeave(CANDIDATE_SCOPE), true)
  current.reason = 'Исправление'
  assert.equal(guard.confirmLeave(CANDIDATE_SCOPE), false)
  unregister()
  assert.equal(guard.confirmLeave(), true)
  assert.equal(prompts.length, 4)
})

test('empty add forms and reverted defaults remain clean; reset after save is clean', () => {
  const initial = { is_confirmed: true, language_id: null, document: '' }
  let baseline = formFingerprint(initial)
  const dirty = form => formFingerprint(form) !== baseline
  assert.equal(dirty(initial), false)
  assert.equal(dirty({ ...initial, is_confirmed: false }), true)
  assert.equal(dirty({ ...initial, language_id: '' }), false)
  const entered = { ...initial, language_id: 2, document: 'certificate' }
  assert.equal(dirty(entered), true)
  baseline = formFingerprint(initial)
  assert.equal(dirty(initial), false)
})

test('dashboard links select exactly the server status and decode a search', () => {
  assert.deepEqual(employeeDirectoryTarget('#/employees?status=in_review'), { search: '', profile_status: 'in_review', create: false })
  assert.equal(employeeDirectoryTarget('#/employees?status=draft').profile_status, 'draft')
  assert.equal(employeeDirectoryTarget('#/employees?status=draft,in_review').profile_status, '')
  assert.equal(employeeDirectoryTarget('#/employees?status=unknown').profile_status, '')
  assert.equal(employeeDirectoryTarget('#/employees?search=%D0%90+%D0%91').search, 'А Б')
  assert.equal(employeeDirectoryTarget('#/employees?create=1').create, true)
  assert.equal(employeeDirectoryTarget('#/employees?search=' + 'a'.repeat(300)).search.length, 200)
})

test('assessment distinguishes stale saved values, preview, unsaved edits and history', () => {
  const saved = { hasSavedScore: true }
  assert.equal(evaluationDisplayState(saved), 'saved')
  assert.equal(evaluationDisplayState({ ...saved, stale: true }), 'stale')
  assert.equal(evaluationDisplayState({ ...saved, stale: true, dirty: true }), 'stale')
  assert.equal(evaluationDisplayState({ ...saved, stale: true, preview: true, dirty: true }), 'preview')
  assert.equal(evaluationDisplayState({ ...saved, historical: true, stale: true }), 'historical')
  assert.equal(evaluationDisplayState({ ...saved, dirty: true }), 'unsaved')
  assert.equal(evaluationDisplayState({ hasSavedScore: false, stale: true }), 'empty')
})

test('existing matching results take priority; closed vacancies offer no new run', () => {
  const vacancy = { id: 4, status: 'active' }
  assert.deepEqual(recruitmentActions(vacancy, null), { primary: { kind: 'start', vacancy: 4 }, secondary: null })
  assert.deepEqual(recruitmentActions(vacancy, { id: 8 }), { primary: { kind: 'results', run: 8 }, secondary: { kind: 'rerun', vacancy: 4 } })
  assert.deepEqual(recruitmentActions({ ...vacancy, status: 'closed' }, { id: 8 }), { primary: { kind: 'results', run: 8 }, secondary: null })
  assert.deepEqual(recruitmentActions({ ...vacancy, status: 'closed' }, null), { primary: null, secondary: null })
})

test('profile action and draft warning labels exist in both languages', () => {
  const ru = employeeDirectoryText('ru'), kk = employeeDirectoryText('kk')
  assert.deepEqual(Object.keys(ru).sort(), Object.keys(kk).sort())
  for (const key of Object.keys(ru)) {
    assert.ok(ru[key] && kk[key], key)
  }
})
