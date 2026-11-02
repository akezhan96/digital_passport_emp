import http from './api'

const tabs = '/api/v1/dossier-subsections'
const profile = (employee, tab) => `/api/v1/employees/${employee}/dossier-subsections/${tab}`
export const dossierSubsectionsApi = {
  tabs: (includeArchived, signal) => http.get(tabs, { params: { include_archived: includeArchived }, signal }),
  detail: (employee, tab, includeArchived, signal) => http.get(profile(employee, tab), { params: { include_archived_fields: includeArchived }, signal }),
  createTab: body => http.post(tabs, body),
  editTab: (id, body) => http.patch(`${tabs}/${id}`, body),
  createField: (tab, body) => http.post(`${tabs}/${tab}/fields`, body),
  editField: (tab, field, body) => http.patch(`${tabs}/${tab}/fields/${field}`, body),
  createEntry: (employee, tab, body) => http.post(`${profile(employee, tab)}/entries`, body),
  editEntry: (employee, tab, entry, body) => http.patch(`${profile(employee, tab)}/entries/${entry}`, body),
  removeEntry: (employee, tab, entry, revision) => http.delete(`${profile(employee, tab)}/entries/${entry}`, { params: { expected_revision: revision } }),
}
