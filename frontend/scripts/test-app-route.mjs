import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveAppRoute, employeeRouteTarget, customTabId, profileHref, routeMountKey } from '../src/appRoute.js'
import { installGuardedHashNavigation } from '../src/unsavedChanges.js'

const pages = { dashboard: true, employees: true, matching: true, vacancies: true }
test('deep links retain their record and tab while invalid screens fall back', () => {
  assert.equal(resolveAppRoute('#/matching?run=59&result=123', pages), 'matching?run=59&result=123')
  assert.equal(resolveAppRoute('#/vacancies?vacancy=3', pages), 'vacancies?vacancy=3')
  assert.equal(resolveAppRoute('#/constructor?employee=3', pages), 'dashboard')
  assert.equal(resolveAppRoute('#/toString', pages), 'dashboard')
})
test('employee links validate IDs and only allow supported profile tabs', () => {
  const tabs = ['general', 'candidate', 'career']
  assert.deepEqual(employeeRouteTarget('#/employees?employee=42&tab=candidate', tabs), { employeeId: 42, tab: 'candidate' })
  for (const id of ['0', '-1', '1.5', '1e2', '9007199254740993', 'no']) {
    assert.equal(employeeRouteTarget(`#/employees?employee=${id}`, tabs).employeeId, null)
  }
  assert.equal(employeeRouteTarget('#/employees?employee=1&tab=unknown', tabs).tab, 'general')
  assert.deepEqual(employeeRouteTarget('#/employees?employee=42&tab=candidate&evaluation=18', tabs),
    { employeeId: 42, tab: 'candidate', evaluationId: 18 })
  for (const query of ['employee=42&tab=general&evaluation=18', 'employee=42&tab=candidate&evaluation=-1', 'tab=candidate&evaluation=18'])
    assert.equal(employeeRouteTarget('#/employees?' + query, tabs).evaluationId, undefined)
})
test('same-page record links and Back respect unsaved data and retain full previous URL', () => {
  let handler, committed, allow = false, replaced
  const target = {
    location: { pathname: '/', search: '', hash: '#/employees?employee=1&tab=candidate' },
    history: { state: null, replaceState: (_state, _title, url) => { replaced = url; target.location.hash = url.slice(url.indexOf('#')) } },
    addEventListener: (_event, fn) => { handler = fn }, removeEventListener: () => {},
  }
  const cleanup = installGuardedHashNavigation({ target, resolvePage: () => resolveAppRoute(target.location.hash, pages),
    initialPage: 'employees?employee=1&tab=candidate', commitPage: route => { committed = route }, confirmLeave: () => allow })
  target.location.hash = '#/employees?employee=2&tab=career'
  handler()
  assert.equal(committed, undefined)
  assert.equal(replaced, '/#/employees?employee=1&tab=candidate')
  allow = true
  target.location.hash = '#/employees?employee=2&tab=career'
  handler()
  assert.equal(committed, 'employees?employee=2&tab=career')
  allow = false
  target.location.hash = '#/employees?employee=1&tab=candidate'
  handler()
  assert.equal(replaced, '/#/employees?employee=2&tab=career')
  cleanup()
})

test('top-level custom tabs have stable URLs and preserve the current directory filters', () => {
  const route = 'employees?status=draft&employee=42&tab=candidate&evaluation=18'
  const href = profileHref(route,42,'custom-7')
  assert.deepEqual(employeeRouteTarget(href,['general','candidate']), { employeeId: 42, tab: 'custom-7' })
  assert.equal(routeMountKey(href.slice(2)), routeMountKey(route))
  assert.equal(profileHref(route,null), '#/employees?status=draft')
  for (const invalid of ['custom-0','custom--1','custom-9007199254740993','custom-2x']) {
    assert.equal(customTabId(invalid), null)
  }
})
