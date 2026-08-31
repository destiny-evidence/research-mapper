// The full record: everything the session produced, assembled from routes that
// already exist. See docs/08-web-ui-plan.md §6 for what it deliberately misses.

import * as api from './api.js'

/**
 * Fetch the whole session as one object. Pure enough to test by passing a stub
 * client; nothing here touches the DOM.
 */
export async function buildRecord(sessionId, client = api) {
  const session = await client.getSession(sessionId)
  const operationIds = await client.listOperationIds(sessionId)

  // Operations carry their own decisions, so there is no separate call for them.
  const operations = await Promise.all(operationIds.map((id) => client.getOperation(id)))
  const types = Object.keys(session.artifacts ?? {})
  const payloads = await Promise.all(types.map((type) => client.getArtifact(sessionId, type)))
  // Nothing in the UI shows these, but they carry why each reference was set
  // aside, which is the question the map provokes.
  const references = await client.listReferences(sessionId).catch(() => [])

  return {
    exported_at: new Date().toISOString(),
    session,
    operations,
    artifacts: Object.fromEntries(types.map((type, i) => [type, payloads[i]])),
    references,
    // A session without a map is the normal case for most of its life.
    map: await client.getMap(sessionId).catch(() => null),
  }
}

export function download(record, filename) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export async function downloadRecord(sessionId) {
  const record = await buildRecord(sessionId)
  download(record, `research-mapper-${sessionId.slice(0, 8)}.json`)
}
