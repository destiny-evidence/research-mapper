import * as api from "./api.js";

/** Fetch the whole session as one object for auditing. */
export async function buildRecord(sessionId, client = api) {
  const session = await client.getSession(sessionId);
  const operationIds = await client.listOperationIds(sessionId);

  const operations = await Promise.all(
    operationIds.map((id) => client.getOperation(id)),
  );
  const types = Object.keys(session.artifacts ?? {});
  const payloads = await Promise.all(
    types.map((type) => client.getArtifact(sessionId, type)),
  );
  const references = await client
    .listReferences(sessionId, { includeEvidence: true })
    .catch(() => []);
  const map = await client
    .getMap(sessionId, { includeEvidence: false })
    .catch(() => null);

  return {
    exported_at: new Date().toISOString(),
    session,
    operations,
    artifacts: Object.fromEntries(types.map((type, i) => [type, payloads[i]])),
    references,
    map: withEvidence(map, references),
  };
}

/**
 * The map's evidence is the same records the references carry, and hydrating
 * either costs a repository lookup per hundred ids, so the map is fetched with
 * ids only and joined to what the references already fetched.
 */
function withEvidence(map, references) {
  if (!map?.mapped_evidence) return map;
  const known = new Map(
    references.map((reference) => [reference.destiny_id, reference.evidence]),
  );
  return {
    ...map,
    mapped_evidence: map.mapped_evidence.map((item) => ({
      ...item,
      evidence: known.get(item.evidence?.destiny_id) ?? item.evidence,
    })),
  };
}

export function download(record, filename) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(record, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export async function downloadRecord(sessionId) {
  const record = await buildRecord(sessionId);
  download(record, `research-mapper-${sessionId.slice(0, 8)}.json`);
}
