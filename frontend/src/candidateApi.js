import http from './api'
const root = '/api/v1/methodology'
export const candidateApi = {
  models: () => http.get(`${root}/candidate-models`),
  create: body => http.post(`${root}/candidate-models`, body),
  remove: id => http.delete(`${root}/candidate-models/${id}`),
  model: (id, signal) => http.get(`${root}/candidate-models/${id}`, { signal }),
  clone: id => http.post(`${root}/candidate-models/${id}/clone`),
  update: (id, body) => http.put(`${root}/candidate-models/${id}`, body),
  activate: (id, revision) => http.post(`${root}/candidate-models/${id}/activate`, { expected_revision: revision }),
  matrix: (params, signal) => http.get(`${root}/candidate-matrix`, { params, signal }),
  evaluation: (id, evaluation_id, signal, methodology_id) => http.get(`${root}/employees/${id}/evaluation`, { params: { evaluation_id, methodology_id }, signal }),
  saveEvaluation: (id, body) => http.put(`${root}/employees/${id}/evaluation`, body),
  history: (id, offset = 0) => http.get(`${root}/employees/${id}/evaluation-history`, { params: { offset, limit: 20 } }),
  sources: signal => http.get(`${root}/candidate-sources`, { signal }),
  preview: (id, body) => http.post(`${root}/employees/${id}/evaluation-preview`, body),
  fields: signal => http.get('/api/v1/custom-fields', { params: { entity_type: 'employee', include_inactive: true }, signal }),
  createField: body => http.post('/api/v1/custom-fields', { ...body, entity_type: 'employee' }),
  updateField: (id, body) => http.put(`/api/v1/custom-fields/${id}`, body),
  removeField: id => http.delete(`/api/v1/custom-fields/${id}`),
  fieldValues: (id, signal) => http.get(`/api/v1/custom-values/employee/${id}`, { signal }),
  saveFieldValues: (id, values) => http.put(`/api/v1/custom-values/employee/${id}`, { values }),
}
