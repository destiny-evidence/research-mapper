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
  const references = await allReferences(sessionId, client).catch(() => []);
  const map = await client.getMap(sessionId).catch(() => null);

  return {
    exported_at: new Date().toISOString(),
    session,
    operations,
    artifacts: Object.fromEntries(types.map((type, i) => [type, payloads[i]])),
    references,
    map,
  };
}

// The largest page the API serves without evidence.
const RECORD_PAGE = 1000;

/**
 * Every reference, a page at a time, with what the session recorded about each
 * but not its bibliographic detail: the repository stays the source of that, and
 * looking up every reference would cost a DESTINY lookup per hundred.
 */
async function allReferences(sessionId, client) {
  const references = [];
  let after = null;
  do {
    const page = await client.listReferences(sessionId, {
      after,
      limit: RECORD_PAGE,
    });
    references.push(...page.items);
    after = page.next;
  } while (after);
  return references;
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
