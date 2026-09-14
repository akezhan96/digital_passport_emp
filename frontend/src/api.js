import axios from 'axios'

const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const http = axios.create({
  baseURL: BASE,
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
  return config
})

/** Pull a readable message out of a FastAPI error body. */
export function errorMessage(err) {
  const detail = err?.response?.data?.detail
  if (!detail) return err?.message || 'Request failed'
  if (typeof detail === 'string') return detail
  if (detail.message) {
    const extra = detail.hint || detail.valid_levels?.join(', ') || ''
    return extra ? `${detail.message} ${extra}` : detail.message
  }
  if (Array.isArray(detail)) return detail.map((d) => d.msg).join('; ')
  return JSON.stringify(detail)
}

export const api = {
  // ---- auth --------------------------------------------------------------
  login: (username, password) =>
    http.post('/api/v1/auth/login', { username, password }),
  me: () => http.get('/api/v1/auth/me'),

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
  employeeUpdate: (id, body) => http.put(`/api/v1/employees/${id}`, body),
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
  matchingResults: (runId, revealNames = false) =>
    http.get(`/api/v1/matching-runs/${runId}/results`,
      { params: { reveal_names: revealNames } }),
  runsForVacancy: (vacancyId) => http.get(`/api/v1/vacancies/${vacancyId}/matching-runs`),
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
    `${BASE}/api/v1/attachments/${id}/download`
    + (authToken ? `?token=${encodeURIComponent(authToken)}` : ''),

  auditLog: (params) => http.get('/api/v1/audit-log', { params }),
}

export default http
