import test from 'node:test'
import assert from 'node:assert/strict'
import { candidatePointsPreview, pointsToHundredths } from '../src/candidatePoints.js'
import { createUnsavedChangesGuard, installGuardedHashNavigation,
  CANDIDATE_SCOPE, METHODOLOGY_SCOPE } from '../src/unsavedChanges.js'
import { candidateDictionaries } from '../src/i18n/candidateMethodology.js'

const criterion = (position, maximum, block = 'general', enabled = true) => ({ position, max_points: maximum, block, enabled })

test('percentage ties match Decimal HALF_UP rather than binary floating point', () => {
  const rows = [criterion(3, 200)]
  for (const [points, expected] of [['2.01', 1.01], ['1.99', 1], ['2.03', 1.02], ['199.99', 100], ['0.01', 0.01]]) {
    assert.equal(candidatePointsPreview(rows, { 3: points }, false).percent, expected, points)
  }
})

test('zero, maximum and missing values remain distinct', () => {
  const rows = [criterion(3, 15)]
  assert.equal(candidatePointsPreview(rows, { 3: '0' }, false).earned_points, 0)
  assert.equal(candidatePointsPreview(rows, { 3: '0' }, false).percent, 0)
  assert.equal(candidatePointsPreview(rows, { 3: '15' }, false).percent, 100)
  const missing = candidatePointsPreview(rows, { 3: '' }, false)
  assert.equal(missing.earned_points, null)
  assert.equal(missing.percent, null)
  assert.equal(missing.missing_count, 1)
  assert.equal(missing.max_points, 15)
})

test('all 44 fractional scores aggregate exactly without float drift', () => {
  const rows = Array.from({ length: 44 }, (_, index) => criterion(index + 3, '0.30'))
  const values = Object.fromEntries(rows.map(c => [c.position, '0.10']))
  const summary = candidatePointsPreview(rows, values, true)
  assert.equal(summary.earned_points, 4.4)
  assert.equal(summary.max_points, 13.2)
  assert.equal(summary.percent, 33.33)
  assert.equal(summary.filled_count, 44)
  assert.equal(summary.complete, true)
})

test('500 maximum allowed scores remain within exact integer range', () => {
  const rows = Array.from({ length: 500 }, (_, index) => criterion(index + 3, 10000))
  const values = Object.fromEntries(rows.map(c => [c.position, '10000.00']))
  const summary = candidatePointsPreview(rows, values, true)
  assert.equal(summary.earned_points, 5000000)
  assert.equal(summary.max_points, 5000000)
  assert.equal(summary.percent, 100)
})

test('dynamic criteria with sparse stable keys retain scores after section reorder', () => {
  const rows = [criterion(1004, '8.25'), criterion(47, '10.50'), criterion(3, '3.25', 'technical')]
  const scores = { 1004: '4.25', 47: '8.50', 3: '3.25' }
  const before = candidatePointsPreview(rows, scores, true)
  assert.equal(before.earned_points, 16)
  assert.equal(before.max_points, 22)
  assert.equal(before.percent, 72.73)
  assert.deepEqual(candidatePointsPreview([...rows].reverse(), scores, true), before)
})

test('technical and disabled criteria are excluded before aggregation', () => {
  const rows = [criterion(3, 5), criterion(35, 10, 'technical'), criterion(4, 20, 'general', false)]
  const values = { 3: '5', 35: '10', 4: '20' }
  assert.equal(candidatePointsPreview(rows, values, false).earned_points, 5)
  assert.equal(candidatePointsPreview(rows, values, false).max_points, 5)
  assert.equal(candidatePointsPreview(rows, values, true).earned_points, 15)
  assert.equal(candidatePointsPreview(rows, values, true).max_points, 15)
})

test('missing values do not inflate a partially filled assessment', () => {
  const summary = candidatePointsPreview([criterion(3, 10), criterion(4, 10)], { 3: '10' }, false)
  assert.equal(summary.percent, 50)
  assert.equal(summary.max_points, 20)
  assert.equal(summary.filled_count, 1)
  assert.equal(summary.complete, false)
})

test('invalid precision, negative, excessive and nonfinite inputs do not show a plausible percentage', () => {
  for (const value of ['0.001', '-1', 'NaN', 'Infinity', '5.01', '1e100000', 'invalid']) {
    const summary = candidatePointsPreview([criterion(3, 5)], { 3: value }, false)
    assert.equal(summary.percent, null, value)
    assert.equal(summary.invalid_count, 1, value)
    assert.equal(summary.complete, false, value)
  }
})

test('valid decimal and exponent notations convert without a float round trip', () => {
  for (const [value, expected] of [['2.01', 201n], ['2.01e0', 201n], ['201e-2', 201n],
    ['1e2', 10000n], ['.05', 5n], ['+2.0100', 201n], ['0.00', 0n]]) {
    assert.equal(pointsToHundredths(value), expected, value)
  }
  assert.equal(candidatePointsPreview([criterion(3, '2e2')], { 3: '201e-2' }, false).percent, 1.01)
})

test('preview preserves server privacy flag and reports incomplete totals', () => {
  const summary = candidatePointsPreview([criterion(3, 20)], {}, false, { partial_visibility: true, version: 2 })
  assert.equal(summary.partial_visibility, true)
  assert.equal(summary.version, 2)
  assert.equal(summary.percent, null)
})

function fakeWindow() {
  const listeners = new Map()
  const target = {
    location: { pathname: '/app', search: '?local=1', hash: '#/employees' },
    addEventListener(type, fn) { if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(fn) },
    removeEventListener(type, fn) { listeners.get(type)?.delete(fn) },
    dispatch(type, event = {}) { for (const fn of listeners.get(type) || []) fn(event) },
    listenerCount(type) { return listeners.get(type)?.size || 0 },
  }
  target.history = { state: {}, replacements: [], replaceState(state, _, url) {
    this.state = state; this.replacements.push(url); target.location.hash = new URL(url, 'http://localhost').hash
  } }
  return target
}

function fixture(dirty = true, lang = 'ru') {
  const target = fakeWindow(), prompts = [], state = { dirty, message: candidateDictionaries[lang].discard }
  let answer = false
  const guard = createUnsavedChangesGuard({ target, confirm: message => { prompts.push(message); return answer } })
  const unregister = guard.register(() => state, CANDIDATE_SCOPE)
  return { target, prompts, state, guard, unregister, answer: value => { answer = value } }
}

test('a clean form does not prompt for local navigation or browser reload', () => {
  const f = fixture(false)
  assert.equal(f.guard.confirmLeave(), true)
  let prevented = false
  f.target.dispatch('beforeunload', { preventDefault() { prevented = true } })
  assert.equal(prevented, false)
  assert.deepEqual(f.prompts, [])
})

test('cancelled modal Close or Esc preserves the form and cancels native dialog dismissal', () => {
  const f = fixture()
  for (const action of ['Close', 'Escape']) {
    let closed = false, cancelled = false
    const allowed = f.guard.run(() => { closed = true }, {
      scope: CANDIDATE_SCOPE, event: { preventDefault() { cancelled = true } },
    })
    assert.equal(allowed, false, action)
    assert.equal(closed, false, action)
    assert.equal(cancelled, true, action)
    assert.equal(f.state.dirty, true)
  }
})

test('accepted modal/tab departure runs once; a failed action does not silently clear dirty state', () => {
  const f = fixture(); f.answer(true)
  let count = 0
  assert.equal(f.guard.run(() => { count += 1 }, { scope: CANDIDATE_SCOPE }), true)
  assert.equal(count, 1)
  assert.equal(f.prompts.length, 1)
  assert.equal(f.state.dirty, true)
})

test('successful save removes the prompt without intercepting submit or other form clicks', () => {
  const f = fixture()
  assert.equal(f.target.listenerCount('click'), 0)
  assert.equal(f.target.listenerCount('submit'), 0)
  f.state.dirty = false
  assert.equal(f.guard.confirmLeave(), true)
  assert.deepEqual(f.prompts, [])
})

test('reload registers a native warning and uses the current locale', () => {
  const f = fixture()
  f.state.message = candidateDictionaries.kk.discard
  let prevented = false
  const event = { preventDefault() { prevented = true } }
  f.target.dispatch('beforeunload', event)
  assert.equal(prevented, true)
  assert.equal(event.returnValue, candidateDictionaries.kk.discard)
  f.guard.confirmLeave()
  assert.deepEqual(f.prompts, [candidateDictionaries.kk.discard])
})

test('closing a clean assessment does not discard or warn about a different method draft', () => {
  const f = fixture(false)
  const removeMethod = f.guard.register(() => ({ dirty: true, message: 'Method draft' }), METHODOLOGY_SCOPE)
  let closed = false
  assert.equal(f.guard.run(() => { closed = true }, { scope: CANDIDATE_SCOPE }), true)
  assert.equal(closed, true)
  assert.deepEqual(f.prompts, [])
  assert.equal(f.guard.confirmLeave(), false)
  assert.deepEqual(f.prompts, ['Method draft'])
  removeMethod()
})

test('unmount removes only its own registration and the last beforeunload listener', () => {
  const f = fixture()
  const removeSecond = f.guard.register(() => ({ dirty: false, message: '' }), METHODOLOGY_SCOPE)
  assert.equal(f.target.listenerCount('beforeunload'), 1)
  f.unregister()
  assert.equal(f.guard.confirmLeave(), true)
  assert.equal(f.target.listenerCount('beforeunload'), 1)
  removeSecond()
  assert.equal(f.target.listenerCount('beforeunload'), 0)
})

test('cancelled sidebar and browser Back transitions retain the current page and restore URL', () => {
  const f = fixture(), committed = []
  const remove = installGuardedHashNavigation({ target: f.target, initialPage: 'employees',
    resolvePage: () => f.target.location.hash.slice(2), commitPage: page => committed.push(page),
    confirmLeave: () => f.guard.confirmLeave() })
  for (const page of ['structure', 'methodology']) {
    f.target.location.hash = `#/${page}`
    f.target.dispatch('hashchange')
    assert.equal(f.target.location.hash, '#/employees')
    assert.deepEqual(committed, [])
  }
  assert.deepEqual(f.target.history.replacements, ['/app?local=1#/employees', '/app?local=1#/employees'])
  remove()
  assert.equal(f.target.listenerCount('hashchange'), 0)
})

test('accepted navigation commits once, same-page hash and new windows do not prompt', () => {
  const f = fixture(), committed = []
  installGuardedHashNavigation({ target: f.target, initialPage: 'employees',
    resolvePage: () => f.target.location.hash.slice(2), commitPage: page => committed.push(page),
    confirmLeave: () => f.guard.confirmLeave() })
  // A separate window does not dispatch hashchange on this one; same-page
  // navigation likewise must not discard a form or ask for confirmation.
  f.target.dispatch('hashchange')
  assert.deepEqual(f.prompts, [])
  f.answer(true)
  f.target.location.hash = '#/structure'; f.target.dispatch('hashchange')
  assert.deepEqual(committed, ['structure'])
  assert.equal(f.prompts.length, 1)
  f.target.dispatch('hashchange')
  assert.equal(f.prompts.length, 1)
})
