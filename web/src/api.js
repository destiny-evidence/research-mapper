// The only module that knows about HTTP. Route changes stop here.

import { authHeaders } from './auth.js'

const BASE = import.meta.env?.VITE_API_BASE ?? '/api'

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `request failed (${status})`)
    this.status = status
    this.detail = detail
  }
}

async function request(path, { method = 'GET', body } = {}) {
  const response = await fetch(BASE + path, {
    method,
    headers: { ...authHeaders(), ...(body ? { 'content-type': 'application/json' } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response))
  }
  return response.status === 204 ? null : response.json()
}

async function detailOf(response) {
  try {
    const body = await response.json()
    return typeof body?.detail === 'string' ? body.detail : JSON.stringify(body?.detail ?? body)
  } catch {
    return null
  }
}

export const createSession = (body) => request('/sessions/', { method: 'POST', body })
export const listSessions = () => request('/sessions/')
export const getSession = (id) => request(`/sessions/${id}/`)

export const startOperation = (sessionId, type, params = {}) =>
  request(`/sessions/${sessionId}/operations/`, { method: 'POST', body: { type, params } })

// Returns ids only — the full operations are fetched one at a time.
export const listOperationIds = (sessionId) => request(`/sessions/${sessionId}/operations/`)
export const getOperation = (id) => request(`/operations/${id}/`)

export const respond = (operationId, answers) =>
  request(`/operations/${operationId}/respond/`, { method: 'POST', body: { answers } })
export const retry = (operationId) => request(`/operations/${operationId}/retry/`, { method: 'POST' })

// Unanswered by default. Every open question in a session, across operations —
// the session view reads them off each operation instead, but this is the cheap
// way to answer "does this session need me?" in one call.
export const listDecisions = (sessionId, { unanswered = true } = {}) =>
  request(`/sessions/${sessionId}/decisions/?unanswered=${unanswered}`)

export const getArtifact = (sessionId, type) => request(`/sessions/${sessionId}/artifacts/${type}/`)
// Hydrating the evidence is a DESTINY lookup per hundred references and most
// of what this call costs. The map view only needs coordinates.
// Every reference, every stage, no paging — the only source of per-reference
// screening and mapping reasoning. Record download only for now.
export const listReferences = (sessionId) => request(`/sessions/${sessionId}/references/`)

export const getMap = (sessionId, { includeEvidence = true } = {}) =>
  request(`/sessions/${sessionId}/map/?include_evidence=${includeEvidence}`)
