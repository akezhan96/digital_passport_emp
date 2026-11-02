// Render synthetic fixtures to HTML in Node. This is not a browser/UI automation test.
import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import react from '@vitejs/plugin-react'
import { fileURLToPath } from 'node:url'
import { tmpdir } from 'node:os'
import { join } from 'node:path'

const server = await createServer({ root: fileURLToPath(new URL('..', import.meta.url)), configFile: false,
  cacheDir: join(tmpdir(), 'hr-workflow-render-cache'), optimizeDeps: { noDiscovery: true, include: [] },
  plugins: [react()], server: { middlewareMode: true, hmr: false }, appType: 'custom' })
after(() => server.close())
const { I18nProvider } = await server.ssrLoadModule('/src/i18n/index.jsx')
const { CandidateSummary } = await server.ssrLoadModule('/src/components/CandidateEvaluation.jsx')
const { default: DossierTabs, EntryCard } = await server.ssrLoadModule('/src/components/DossierSubsections.jsx')
const { RecruitmentActions } = await server.ssrLoadModule('/src/components/RecruitmentSummary.jsx')
const { DashboardContent } = await server.ssrLoadModule('/src/pages/Dashboard.jsx')
const { RankingTable } = await server.ssrLoadModule('/src/components/EmployeeRanking.jsx')
const { default: CareerTab, careerTimeline } = await server.ssrLoadModule('/src/components/CareerTab.jsx')
const { PersonnelFacts } = await server.ssrLoadModule('/src/components/PersonnelFacts.jsx')
const { default: AppointmentForm } = await server.ssrLoadModule('/src/components/AppointmentForm.jsx')
const render = (Component, props, lang = 'ru') => {
  globalThis.localStorage = { getItem: () => lang }
  return renderToStaticMarkup(React.createElement(I18nProvider, null, React.createElement(Component, props)))
}
const summary = { earned_points: 70, max_points: 100, percent: 70, filled_count: 8, applicable_count: 10, complete: false, invalid_count: 0 }

test('stale score and recalculation are rendered together without claiming a saved preview', () => {
  const html = render(CandidateSummary, { summary, state: 'stale', onRecalculate: () => {}, sourceHint: 'test hint' })
  assert.match(html, /70%/)
  assert.match(html, /Оценка устарела/)
  assert.match(html, /Пересчитать оценку/)
  assert.match(html, /Заполнено применимых показателей/)
  assert.match(html, /8 \/ 10/)
  assert.doesNotMatch(html, /Сохранённая оценка/)
  const preview = render(CandidateSummary, { summary, state: 'preview', dirty: true })
  assert.match(preview, /Предварительный расчёт/)
  assert.doesNotMatch(preview, /Оценка устарела|Сохранённая оценка/)
})

test('readonly score has no recalculation action, while blocked editing explains why', () => {
  assert.doesNotMatch(render(CandidateSummary, { summary, state: 'stale' }), /<button/)
  const blocked = render(CandidateSummary, { summary, state: 'stale', onRecalculate: () => {}, recalculateDisabled: true, sourceHint: 'Сначала сохраните поля личного дела.' })
  assert.match(blocked, /disabled=""/)
  assert.match(blocked, /Сначала сохраните поля/)
  const kk = render(CandidateSummary, { summary, state: 'stale', onRecalculate: () => {} }, 'kk')
  assert.match(kk, /Баға ескірген/)
  assert.match(kk, /Бағаны қайта есептеу/)
})

test('vacancy action links open a saved run before offering a secondary rerun', () => {
  const html = render(RecruitmentActions, { vacancy: { id: 3, status: 'active' }, latestRun: { id: 12 } })
  assert.match(html, /class="btn btn-sm" href="#\/matching\?run=12"/)
  assert.match(html, /Открыть результаты подбора/)
  assert.match(html, /class="btn btn-sm btn-ghost" href="#\/matching\?vacancy=3"/)
  assert.match(html, /Запустить подбор заново/)
  const closed = render(RecruitmentActions, { vacancy: { id: 3, status: 'closed' }, latestRun: { id: 12 } })
  assert.doesNotMatch(closed, /vacancy=3|Запустить подбор/)
})

const dashboard = { employees: { total: 5, verified: 2, verified_percent: 40, draft: 2, in_review: 0, archived: 1 }, vacancies: { total: 0, active: 0, draft: 0, closed: 0 }, matching_runs: 0, candidate_methodology: null, recent_activity: [] }
test('ranking identifies the saved evaluation only on deliberate name reveal and localizes score context', () => {
  const row = { rank: 2, employee_id: 42, evaluation_id: 18, org_unit: { name_ru: 'Отдел', name_kk: 'Бөлім' },
    earned_points: 7.5, max_points: 10, percent: 75 }
  const hidden = render(RankingTable, { data: { items: [{ ...row, display_name: 'E-001' }], names_revealed: false } })
  assert.match(hidden, /E-001/)
  assert.match(hidden, /7,5<\/strong> \/ 10/)
  assert.match(hidden, /75%/)
  assert.doesNotMatch(hidden, /href=/)
  const shown = render(RankingTable, { data: { items: [{ ...row, display_name: 'Тест' }], names_revealed: true } }, 'kk')
  assert.match(shown, /href="#\/employees\?employee=42&amp;tab=candidate&amp;evaluation=18"/)
  assert.match(shown, /Бағаны ашу: Тест/)
  assert.match(shown, /Бөлім</)
})
test('dashboard puts work before charts and does not call all profiles checked at zero review count', () => {
  const html = render(DashboardContent, { data: dashboard, isAdmin: true, onNavigate: () => {} })
  assert.ok(html.indexOf('dashboard-search') < html.indexOf('dashboard-charts'))
  assert.match(html, /Нет дел на проверке/)
  assert.match(html, /href="#\/employees\?status=draft"/)
  assert.match(html, /href="#\/analytics\?tab=ranking"/)
  assert.doesNotMatch(html, /Все профили проверены|href="#\/employees\?status=in_review"/)
  const review = render(DashboardContent, { data: { ...dashboard, employees: { ...dashboard.employees, in_review: 1 } }, isAdmin: false, onNavigate: () => {} })
  assert.match(review, /href="#\/employees\?status=in_review"/)
  assert.doesNotMatch(review, /Добавить сотрудника/)
})


test('custom tab creation lives in the profile navigation beside built-in tabs, admin only', () => {
  const props = { employeeId: 9, routeKey: 'employees?employee=9', selectedTab: 'documents',
    builtins: [{ key: 'documents', label: 'Документы' }, { key: 'history', label: 'История' }], children: 'Existing form' }
  const html = render(DossierTabs, { ...props, isAdmin: true })
  const nav = html.match(/<nav.*?<\/nav>/s)[0]
  assert.match(nav, /Документы.*История.*Добавить вкладку.*Настроить вкладки/s)
  assert.match(html, /Existing form/)
  assert.doesNotMatch(render(DossierTabs, { ...props, isAdmin: false }), /Добавить вкладку|Настроить вкладки/)
  assert.doesNotMatch(render(DossierTabs, { ...props, selectedTab: 'custom-2' }), /Existing form/)
  assert.match(render(DossierTabs, { ...props, isAdmin: true }, 'kk'), /Қойынды қосу/)
})

test('typed entries preserve false, zero and older free text in view mode', () => {
  const html = render(EntryCard, { entry: { id: 7, title: 'Старый заголовок', description: 'Старое описание', values: { 1: false, 2: 0, 3: '2025-10-01' } },
    fields: [{ id: 1, field_type: 'boolean', name_ru: 'Получен' }, { id: 2, field_type: 'number', name_ru: 'Часы' },
      { id: 3, field_type: 'date', name_ru: 'Дата выдачи' }], canEdit: false })
  assert.match(html, /Старый заголовок.*Старое описание.*Получен.*<dd>Нет<.*Часы.*<dd>0<.*Дата выдачи.*01.10.2025/s)
  assert.doesNotMatch(html, /<button/)
})


test('career shows one row per job, keeps an open external period in history, and opens no form on entry', () => {
  const refs = { positions: [{ id: 1, name_ru: 'Инженер стенда' }], 'org-units': [{ id: 1, name_ru: 'Цех стенда' }] }
  const detail = { id: 1, employment_status: 'active', profile_status: 'verified', current_position_id: 1, current_org_unit_id: 1, work_experience: [
    { id: 1, is_internal: false, external_employer: 'Тестовый завод', external_position_title: 'Техник станка', date_from: '2010-04-01', date_to: null },
    { id: 2, is_internal: true, position_id: 1, org_unit_id: 1, date_from: '2020-01-01', date_to: null },
  ] }
  const html = render(CareerTab, { detail, ref_: refs })
  assert.equal((html.match(/Инженер стенда/g) || []).length, 1)
  assert.equal((html.match(/Техник станка/g) || []).length, 1)
  assert.match(html, /Текущая должность/); assert.match(html,/История работы/)
  assert.match(html,/Оформить кадровое действие/); assert.match(html,/Добавить период работы/)
  assert.doesNotMatch(html, /<form|<table|Удалить период|Отменить назначение/)
  const viewer = render(CareerTab, { detail, ref_: refs, readOnly: true }, 'kk')
  assert.match(viewer,/Қазіргі лауазымы/); assert.doesNotMatch(viewer,/Жұмыс кезеңін қосу|Тағайындауды рәсімдеу/)
})

test('career does not infer a current post from external, future or ambiguous records', () => {
  const a = { id: 1, is_internal: true, org_unit_id: 1, position_id: 1, date_from: '2020-01-01' }
  const b = { ...a, id: 2, org_unit_id: 2 }
  const detail = { employment_status: 'active', profile_status: 'verified', work_experience: [a,b] }
  assert.equal(careerTimeline(detail, '2024-01-01').ambiguous,true)
  const conflict = careerTimeline({ ...detail, work_experience: [a], current_position_id: 99 }, '2024-01-01')
  assert.equal(conflict.current, null); assert.equal(conflict.conflict,true); assert.equal(conflict.history.length, 1)
  assert.equal(careerTimeline({ ...detail, current_org_unit_id: 1 }, '2024-01-01').current.id, 1)
  assert.equal(careerTimeline({ ...detail, work_experience:[{ ...a, is_internal:false },{ ...b, date_from:'2030-01-01' }] }, '2024-01-01').current, null)
  assert.equal(careerTimeline({ ...detail, employment_status: 'terminated', work_experience:[a] }, '2024-01-01').current,null)
})


test('current internal work includes both endpoints of a fixed term, not an expired or future period', () => {
  const detail = { employment_status: 'active', profile_status: 'verified', work_experience: [
    { id: 1, is_internal: true, date_from:'2026-02-01', date_to:'2026-02-14' },
    { id: 2, is_internal: true, date_from:'2026-02-15', date_to:'2026-02-28' },
  ] }
  assert.equal(careerTimeline(detail,'2026-01-31').current,null)
  assert.equal(careerTimeline(detail,'2026-02-01').current.id,1)
  assert.equal(careerTimeline(detail,'2026-02-14').current.id,1)
  assert.equal(careerTimeline(detail,'2026-02-15').current.id,2)
  assert.equal(careerTimeline(detail,'2026-03-01').current,null)
})

test('career action offers exactly appointment and disposal, with no legacy choices', () => {
  const html = render(AppointmentForm, { employeeId: 1 })
  assert.match(html, /value="appointment"[^>]*>Назначение<.*value="disposal">Вывод в распоряжение</s)
  assert.doesNotMatch(html, /value="(?:transfer|initial|promotion|return)"/)
  assert.match(render(AppointmentForm, { employeeId: 1 }, 'kk'), /Қарамағына шығару/)
})

test('personnel facts distinguish an unknown contract end from indefinite and show exact zero and elapsed days', () => {
  const asOf = '2026-11-02'
  const snapshot = { records: [], disposals: [{ days: 4 }], summary: { as_of: asOf,
    tenure: { has_work_periods: true, total_days: 42, company_days: 0 },
    contract: { event_date: asOf, status: 'unknown', remaining_days: null },
    rank: { title: 'Инженер I', event_date: asOf, elapsed_days: 0, planned_date: asOf, until_planned_days: 0 },
    recognition: { title: 'Благодарность', event_date: '2026-10-31', elapsed_days: 2 } } }
  const html = render(PersonnelFacts, { snapshot })
  assert.match(html, /Срок окончания не указан/); assert.doesNotMatch(html,/Бессрочный|Добавить запись/)
  for (const text of ['42 дн.', '0 дн.', '2 дн.', '4 дн.', 'Плановая дата сегодня', '02.11.2026', 'Периоды в распоряжении исключены']) assert.ok(html.includes(text))
  snapshot.summary.contract.status = 'indefinite'
  assert.match(render(PersonnelFacts, { snapshot, canWrite: true }, 'kk'), /Мерзімсіз/)
})

test('long seniority keeps exact days and labels the year estimate', () => {
  const snapshot = { disposals: [], records: [], summary: { as_of: '2026-11-02',
    tenure: { has_work_periods: true, total_days: 3032, company_days: 730 } } }
  const html = render(PersonnelFacts, { snapshot })
  assert.match(html, /≈ 8,3 года/); assert.match(html, /3\s032 дн\./)
  assert.match(render(PersonnelFacts, { snapshot }, 'kk'), /≈ 8,3 жыл/)
})
