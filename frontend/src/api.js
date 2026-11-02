import { renderDemo } from './renderDemo'
import axios from 'axios'
import { localizeText } from './i18n/text'

// Empty means "same origin": in production nginx serves the interface and
// proxies /api, so the browser makes no cross-origin request at all. The
// localhost fallback is for `npm run dev`, where the API is a separate port.
const configured = import.meta.env.VITE_API_BASE_URL
const BASE = configured !== undefined && configured !== null
  ? configured
  : renderDemo ? '' : 'http://localhost:18000'

const http = axios.create({
  baseURL: BASE,
  withCredentials: true,
  headers: { 'Content-Type': 'application/json' },
})

// Held in a module variable so every request picks it up without prop drilling.
let authToken = null

export function setAuthToken(token) {
  authToken = token || null
}

export function getAuthToken() {
  return authToken
}

http.interceptors.request.use((config) => {
  if (authToken) config.headers.Authorization = `Bearer ${authToken}`
  config.headers['Accept-Language'] = localStorage.getItem('hrts.lang') === 'kk' ? 'kk' : 'ru'
  return config
})

/** Pull a readable message out of a FastAPI error body. */
export function errorMessage(err) {
  const detail = err?.response?.data?.detail
  const kk = localStorage.getItem('hrts.lang') === 'kk'
  if (!detail) return kk ? 'Сервермен байланыс жоқ. Қайталап көріңіз.' : 'Нет связи с сервером. Повторите попытку.'
  if (typeof detail === 'string') {
    const pair = detail.split(' / ')
    return localizeText(pair.length === 2 ? pair[kk ? 1 : 0] : detail, kk ? 'kk' : 'ru')
  }
  if (detail.message) {
    const extra = detail.hint || detail.valid_levels?.join(', ') || ''
    return localizeText(extra ? `${detail.message} ${extra}` : detail.message, kk ? 'kk' : 'ru')
  }
  if (Array.isArray(detail)) return kk ? 'Енгізілген деректерді тексеріңіз: міндетті өрістер, күндер және сандар.' : 'Проверьте введённые данные: обязательные поля, даты и числа.'
  return JSON.stringify(detail)
}

export const api = {
  // ---- auth --------------------------------------------------------------
  login: (username, password) =>
    http.post('/api/v1/auth/login', { username, password }),
  me: () => http.get('/api/v1/auth/me'),
  logout: () => http.post('/api/v1/auth/logout'),
  health: () => http.get('/health'),
  assistantStatus: () => http.get('/api/v1/assistant/status'),
  assistantConversations: (offset = 0) => http.get('/api/v1/assistant/conversations', { params: { offset, limit: 50 } }),
  assistantConversationCreate: (conversation_id, title) => http.post('/api/v1/assistant/conversations', { conversation_id, title }),
  assistantHistory: (offset = 0, conversation_id) => http.get('/api/v1/assistant/requests', { params: { offset, conversation_id } }),
  assistantSubmit: (text, lang, request_id, model, conversation_id, mode = 'auto') =>
    http.post('/api/v1/assistant/requests', { text, lang, request_id, model, conversation_id, mode }),
  assistantCancel: id => http.post(`/api/v1/assistant/requests/${id}/cancel`),
  assistantConditions: (id, conditions) => http.post(`/api/v1/assistant/requests/${id}/conditions`, conditions),
  assistantReportPreview: (request_id, spec, reveal_names) => http.post('/api/v1/assistant/reports/preview', { request_id, spec, reveal_names }),
  assistantReports: (conversation_id, request_id, offset = 0) => http.get('/api/v1/assistant/reports', { params: { conversation_id, request_id, offset, limit: 50 } }),
  assistantReport: id => http.get(`/api/v1/assistant/reports/${id}`),
  assistantReportDocument: id => http.post(`/api/v1/assistant/reports/${id}/document`, {}, { responseType: 'blob' }),
  assistantInterpret: (text, lang, signal) =>
    http.post('/api/v1/assistant/interpret', { text, lang }, { timeout: 195000, signal }),

  dashboard: () => http.get('/api/v1/dashboard'),

  // ---- reference catalogues (every criterion is editable here) ----------
  catalogs: () => http.get('/api/v1/reference/catalogs'),
  refList: (catalog) => http.get(`/api/v1/reference/${catalog}`),
  refCreate: (catalog, body) => http.post(`/api/v1/reference/${catalog}`, body),
  refUpdate: (catalog, id, body) => http.put(`/api/v1/reference/${catalog}/${id}`, body),
  refDelete: (catalog, id) => http.delete(`/api/v1/reference/${catalog}/${id}`),

  // ---- employees --------------------------------------------------------
  employees: (params) => http.get('/api/v1/employees', { params }),
  employee: (id) => http.get(`/api/v1/employees/${id}`),
  employeeSummary: (id) => http.get(`/api/v1/employees/${id}/summary`),
  employeeCreate: (body) => http.post('/api/v1/employees', body),
  employeeUpdate: (id, body, reason) =>
    http.put(`/api/v1/employees/${id}`, body,
      reason ? { params: { reason } } : undefined),
  employeeUsage: (id) => http.get(`/api/v1/employees/${id}/usage`),
  employeeDelete: (id, reason) =>
    http.delete(`/api/v1/employees/${id}`,
      reason ? { params: { reason } } : undefined),
  employeeArchive: (id, reason) =>
    http.post(`/api/v1/employees/${id}/archive`, {},
      reason ? { params: { reason } } : undefined),
  employeeRestore: (id) => http.post(`/api/v1/employees/${id}/restore`, {}),
  employeeVerify: (id) => http.post(`/api/v1/employees/${id}/verify`),
  competencyHistory: (id) => http.get(`/api/v1/employees/${id}/competency-history`),

  addEducation: (id, body) => http.post(`/api/v1/employees/${id}/education`, body),
  delEducation: (rowId) => http.delete(`/api/v1/employees/education/${rowId}`),
  addLanguage: (id, body) => http.post(`/api/v1/employees/${id}/languages`, body),
  delLanguage: (rowId) => http.delete(`/api/v1/employees/languages/${rowId}`),
  addTraining: (id, body) => http.post(`/api/v1/employees/${id}/training`, body),
  delTraining: (rowId) => http.delete(`/api/v1/employees/training/${rowId}`),
  addCareer: (id, body) => http.post(`/api/v1/employees/${id}/work-experience`, body),
  delCareer: (rowId) => http.delete(`/api/v1/employees/work-experience/${rowId}`),
  addAssessment: (id, body) => http.post(`/api/v1/employees/${id}/assessments`, body),

  // ---- vacancies & requirements ----------------------------------------
  vacancies: (status) => http.get('/api/v1/vacancies', { params: { status } }),
  vacancy: (id) => http.get(`/api/v1/vacancies/${id}`),
  vacancyRecruitment: (id, params = {}) => http.get(`/api/v1/vacancies/${id}/recruitment`, { params }),
  vacancyCreate: (body) => http.post('/api/v1/vacancies', body),
  vacancyUpdate: (id, body) => http.put(`/api/v1/vacancies/${id}`, body),
  requirements: (vacancyId) => http.get(`/api/v1/vacancies/${vacancyId}/requirements`),
  requirementAdd: (vacancyId, body) =>
    http.post(`/api/v1/vacancies/${vacancyId}/requirements`, body),
  requirementUpdate: (id, body) => http.put(`/api/v1/requirements/${id}`, body),
  requirementDelete: (id) => http.delete(`/api/v1/requirements/${id}`),
  profiles: () => http.get('/api/v1/position-profiles'),

  // ---- methodology ------------------------------------------------------
  scoringModels: () => http.get('/api/v1/methodology/scoring-models'),
  scoringModel: (id) => http.get(`/api/v1/methodology/scoring-models/${id}`),
  modelClone: (id, newVersion) =>
    http.post(`/api/v1/methodology/scoring-models/${id}/clone`, null,
      { params: { new_version: newVersion } }),
  modelApprove: (id, makeDefault) =>
    http.post(`/api/v1/methodology/scoring-models/${id}/approve`, null,
      { params: { make_default: makeDefault } }),
  functionUpdate: (id, body) => http.put(`/api/v1/methodology/functions/${id}`, body),
  compensationUpdate: (id, body) =>
    http.put(`/api/v1/methodology/compensations/${id}`, body),
  bandUpdate: (id, body) => http.put(`/api/v1/methodology/readiness-bands/${id}`, body),

  // ---- matching ---------------------------------------------------------
  runMatching: (body) => http.post('/api/v1/matching-runs', body),
  matchingRuns: (params) => http.get('/api/v1/matching-runs', { params }),
  matchingRun: (id) => http.get(`/api/v1/matching-runs/${id}`),
  matchingResult: (id, revealNames = false) => http.get(`/api/v1/matching-results/${id}`, { params: { reveal_names: revealNames } }),
  matchingResults: (runId, revealNames = false, params = {}) =>
    http.get(`/api/v1/matching-runs/${runId}/results`,
      { params: { ...params, reveal_names: revealNames } }),
  runsForVacancy: (vacancyId, params) => http.get(`/api/v1/vacancies/${vacancyId}/matching-runs`, { params }),
  recordDecision: (resultId, body) =>
    http.post(`/api/v1/matching-results/${resultId}/decision`, body),

  // ---- custom fields & attachments --------------------------------------
  customFields: (entityType) =>
    http.get('/api/v1/custom-fields', { params: { entity_type: entityType } }),
  customFieldCreate: (body) => http.post('/api/v1/custom-fields', body),
  customFieldUpdate: (id, body) => http.put(`/api/v1/custom-fields/${id}`, body),
  customFieldDelete: (id) => http.delete(`/api/v1/custom-fields/${id}`),

  customValues: (entityType, entityId) =>
    http.get(`/api/v1/custom-values/${entityType}/${entityId}`),
  customValuesSave: (entityType, entityId, values) =>
    http.put(`/api/v1/custom-values/${entityType}/${entityId}`, { values }),

  attachments: (entityType, entityId) =>
    http.get(`/api/v1/attachments/${entityType}/${entityId}`),
  attachmentUpload: (entityType, entityId, file, description) => {
    const form = new FormData()
    form.append('file', file)
    if (description) form.append('description', description)
    return http.post(`/api/v1/attachments/${entityType}/${entityId}`, form,
      { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  attachmentDelete: (id) => http.delete(`/api/v1/attachments/${id}`),
  // <img src> and <a href> cannot carry an Authorization header, so the
  // token travels as a query parameter for these two cases only.
  attachmentUrl: (id) =>
    `${BASE}/api/v1/attachments/${id}/download`,

  // ---- analytics ---------------------------------------------------------
  analyticsQuestions: () => http.get('/api/v1/analytics/questions'),
  disposalStatistics: (params, signal) => http.post('/api/v1/analytics/disposal-statistics', params, { signal }),
  analyticsOverview: () => http.get('/api/v1/analytics/overview'),
  employeeRanking: (params, signal) => http.post('/api/v1/analytics/employee-ranking', params, { signal }),
  analyticsRun: (code, params, revealNames = false) =>
    http.post('/api/v1/analytics/run',
      { code, params, reveal_names: revealNames }),

  // ---- appointments / transfers -----------------------------------------
  appointments: (employeeId) =>
    http.get(`/api/v1/employees/${employeeId}/appointments`),
  appointmentCreate: (employeeId, body) =>
    http.post(`/api/v1/employees/${employeeId}/appointments`, body),
  appointmentUndo: (employeeId, rowId) =>
    http.delete(`/api/v1/employees/${employeeId}/appointments/${rowId}`),
  appointFromResult: (resultId, body) =>
    http.post(`/api/v1/matching-results/${resultId}/appoint`, body),

  // ---- corrections -------------------------------------------------------
  updateChild: (section, rowId, body) =>
    http.put(`/api/v1/employees/${section}/${rowId}`, body),
  employeeHistory: (employeeId) =>
    http.get(`/api/v1/employees/${employeeId}/history`),

  // ---- generated documents ----------------------------------------------
  // Browser downloads authenticate with the same HttpOnly session cookie.
  documentDownload: (employeeId, params) => http.get(`/api/v1/employees/${employeeId}/document`, { params, responseType: 'blob' }),
  documentUrl: (employeeId, format, lang) =>
    `${BASE}/api/v1/employees/${employeeId}/document`
    + `?format=${format}&lang=${lang}`,

  // ---- query builder -----------------------------------------------------
  analyticsFields: () => http.get('/api/v1/analytics/fields'),
  analyticsPreview: (definition, groupBy, revealNames = false, lang = 'ru') =>
    http.post('/api/v1/analytics/custom/preview',
      { definition, group_by: groupBy, reveal_names: revealNames, lang }),
  savedQueries: () => http.get('/api/v1/analytics/saved'),
  savedQueryCreate: (body) => http.post('/api/v1/analytics/saved', body),
  savedQueryUpdate: (id, body) => http.put(`/api/v1/analytics/saved/${id}`, body),
  savedQueryDelete: (id) => http.delete(`/api/v1/analytics/saved/${id}`),
  savedQueryRun: (id, revealNames = false, lang = 'ru') =>
    http.post(`/api/v1/analytics/saved/${id}/run`,
      { reveal_names: revealNames, lang }),

  // ---- organisation ------------------------------------------------------
  orgTree: (includeEmployees = true) =>
    http.get('/api/v1/org/tree', { params: { include_employees: includeEmployees } }),
  segments: () => http.get('/api/v1/org/segments'),
  segmentMembers: (code, params) => http.get(`/api/v1/org/segments/${code}`, { params }),
  orgUnitMembers: (id, params) => http.get(`/api/v1/org/units/${id}/members`, { params }),
  unitUsage: (id) => http.get(`/api/v1/org/units/${id}/usage`),
  unitDelete: (id) => http.delete(`/api/v1/org/units/${id}`),
  unitMove: (id, parentId) =>
    http.put(`/api/v1/org/units/${id}/parent`, { parent_id: parentId }),

  // ---- establishment (staffing table) -----------------------------------
  unitStaffing: (id) => http.get(`/api/v1/org/units/${id}/staffing`),
  staffingAdd: (unitId, body) =>
    http.post(`/api/v1/org/units/${unitId}/staffing`, body),
  staffingUpdate: (lineId, body) =>
    http.put(`/api/v1/staffing/${lineId}`, body),
  staffingDelete: (lineId) => http.delete(`/api/v1/staffing/${lineId}`),
  staffingSummary: () => http.get('/api/v1/staffing/summary'),
  staffingVacant: (orgUnitId) =>
    http.get('/api/v1/staffing/vacant',
      { params: orgUnitId ? { org_unit_id: orgUnitId } : {} }),

  // ---- user-defined catalogues ------------------------------------------
  customCatalogs: () => http.get('/api/v1/reference/custom-catalogs/list'),
  customCatalogCreate: (body) =>
    http.post('/api/v1/reference/custom-catalogs/list', body),
  customCatalogUpdate: (id, body) =>
    http.put(`/api/v1/reference/custom-catalogs/list/${id}`, body),
  customCatalogDelete: (id) =>
    http.delete(`/api/v1/reference/custom-catalogs/list/${id}`),

  auditLog: (params) => http.get('/api/v1/audit-log', { params }),
}

export default http
