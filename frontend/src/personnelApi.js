import http from './api'

const path = id => `/api/v1/employees/${id}`
export const personnelApi = {
  summary: (id, signal) => http.get(`${path(id)}/personnel-summary`, { signal }),
  records: (id, signal) => http.get(`${path(id)}/personnel-records`, { signal }),
  disposals: (id, signal) => http.get(`${path(id)}/disposals`, { signal }),
  undoDisposal: (id, period) => http.delete(`${path(id)}/disposals/${period}`),
  save: (id, record, body) => record
    ? http.put(`${path(id)}/personnel-records/${record.id}`, { ...body, expected_revision: record.revision })
    : http.post(`${path(id)}/personnel-records`, body),
  remove: (id, record) => http.delete(`${path(id)}/personnel-records/${record.id}`, { params: { expected_revision: record.revision } }),
}
