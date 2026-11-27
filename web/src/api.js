import { authHeaders } from "./auth.js";

const BASE = import.meta.env?.VITE_API_BASE ?? "/api";

export class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `request failed (${status})`);
    this.status = status;
    this.detail = detail;
  }
}

async function request(path, { method = "GET", body } = {}) {
  const response = await fetch(BASE + path, {
    method,
    headers: {
      ...(await authHeaders()),
      ...(body ? { "content-type": "application/json" } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!response.ok) {
    throw new ApiError(response.status, await detailOf(response));
  }
  return response.status === 204 ? null : response.json();
}

async function detailOf(response) {
  try {
    const body = await response.json();
    return typeof body?.detail === "string"
      ? body.detail
      : JSON.stringify(body?.detail ?? body);
  } catch {
    return null;
  }
}

export const createSession = (body) =>
  request("/sessions/", { method: "POST", body });
export const listSessions = () => request("/sessions/");
export const getSession = (id) => request(`/sessions/${id}/`);

export const forkSession = (id, body) =>
  request(`/sessions/${id}/fork/`, { method: "POST", body });

export const startOperation = (sessionId, type, params = {}) =>
  request(`/sessions/${sessionId}/operations/`, {
    method: "POST",
    body: { type, params },
  });

// Returns ids only, the full operations are fetched one at a time.
export const listOperationIds = (sessionId) =>
  request(`/sessions/${sessionId}/operations/`);
export const getOperation = (id) => request(`/operations/${id}/`);

export const respond = (operationId, answers) =>
  request(`/operations/${operationId}/respond/`, {
    method: "POST",
    body: { answers },
  });
export const retry = (operationId) =>
  request(`/operations/${operationId}/retry/`, { method: "POST" });

export const getArtifact = (sessionId, type) =>
  request(`/sessions/${sessionId}/artifacts/${type}/`);

/**
 * One page of a session's references, as a view sees them. `cell` is a list of
 * [dimension, subtopic] pairs; `after` is the previous page's `next`.
 */
export function listReferences(
  sessionId,
  {
    view = "all",
    bucket = null,
    cell = null,
    after = null,
    limit = 50,
    includeEvidence = false,
  } = {},
) {
  const params = new URLSearchParams({
    view,
    limit: String(limit),
    include_evidence: String(includeEvidence),
  });
  if (bucket) params.set("bucket", bucket);
  if (cell?.length) params.set("cell", JSON.stringify(cell));
  if (after) params.set("after", after);
  return request(`/sessions/${sessionId}/references/?${params}`);
}

export const getMap = (sessionId) => request(`/sessions/${sessionId}/map/`);

export const getConfig = () => request("/config");
