// Pure functions over API payloads.

import { MAP_TAILS, planFor, tailOf } from "./plan.js";

/** Newest operation per step type. */
export function byType(operations) {
  const newest = {};
  for (const operation of operations) {
    if (operation?.type) newest[operation.type] = operation;
  }
  return newest;
}

const STATE = {
  pending: "running",
  running: "running",
  awaiting_input: "ask",
  complete: "done",
  failed: "failed",
};

/** The UI state of a step, given its operation (or none). */
export const stateOf = (operation) =>
  operation ? (STATE[operation.status] ?? "todo") : "todo";

const plural = (n, one, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

// One formatter per step type, with a generic fallback.
const RESULT = {
  enhance_sparse_query: (r) => `selected ${r.selected} of ${r.suggested}`,
  generate_screening_criteria: (r) =>
    `selected ${r.selected} of ${r.suggested}`,
  retrieve_sparse_evidence: (r) =>
    join([
      plural(r.references, "reference"),
      r.failed ? `${r.failed} queries failed` : null,
    ]),
  retrieve_concept_evidence: (r) => plural(r.references, "reference"),
  generate_concept_filters: (r, operation) =>
    join([
      plural(r.filter_groups, "group"),
      operation?.decisions?.length
        ? plural(operation.decisions.length, "question")
        : null,
    ]),
  screen_evidence: (r) =>
    join([
      `${r.included} included`,
      `${r.screened - r.included - (r.failed ?? 0)} excluded`,
      r.failed ? `${r.failed} failed` : null,
    ]),
  generate_map_dimensions: (r) => plural(r.dimensions, "dimension"),
  generate_map_subtopics: (r) =>
    join([plural(r.dimensions, "dimension"), plural(r.subtopics, "subtopic")]),
  generate_map: (r) =>
    join([`${r.mapped} placed`, r.failed ? `${r.failed} failed` : null]),
  generate_taxonomy_map: (r) =>
    join([`${r.mapped} placed`, r.dropped ? `${r.dropped} dropped` : null]),
};

const join = (parts) => parts.filter(Boolean).join(" · ");

const genericResult = (result) =>
  Object.entries(result)
    .filter(([key]) => key !== "version")
    .map(([key, value]) => `${key.replace(/_/g, " ")} ${value}`)
    .join(" · ");

/** Progress of a running operation, e.g. "254 of 530". */
export function progressText(progress) {
  if (!progress?.total) return progress?.note || "Thinking";
  return join([
    `${progress.done} of ${progress.total}`,
    progress.failed ? `${progress.failed} failed` : null,
  ]);
}

export const hasCounts = (progress) => Boolean(progress?.total);

export function summarise(operation) {
  if (!operation) return "";
  if (operation.status === "failed") return "Failed";
  if (operation.status === "awaiting_input") return "";
  if (operation.status === "pending") return "Queued";
  if (operation.status === "complete" && operation.result) {
    const format = RESULT[operation.type];
    try {
      return format
        ? format(operation.result, operation)
        : genericResult(operation.result);
    } catch {
      return genericResult(operation.result);
    }
  }
  return progressText(operation.progress);
}

export const MAP_BRANCH = "choose-how-to-map";

export function steps({ session, operations = [] }) {
  const newest = byType(operations);
  const tail = tailOf(operations);
  const rows = planFor(session?.params, tail).map((step) => {
    const operation = newest[step.type];
    const questions = operation?.pending_questions ?? [];
    return {
      ...step,
      operation,
      state: stateOf(operation),
      summary: summarise(operation),
      questions,
    };
  });

  if (tail) return rows;
  const reachable = rows.every((row) => row.state === "done");
  return [
    ...rows,
    {
      type: MAP_BRANCH,
      title: "Build the map",
      state: reachable ? "ask" : "todo",
      summary: "",
      branch: reachable ? MAP_TAILS : null,
      questions: [],
    },
  ];
}

/** The step the client should queue next, or null. */
export function nextToStart(rows) {
  const next = rows.find((row) => row.state !== "done");
  // A branch is the user's to resolve; queueing anything past it would be
  // guessing which map they want.
  if (!next || next.branch) return null;
  return next.operation ? null : next.type;
}

export const mapIsReady = (rows) =>
  rows.some(
    (row) =>
      ["generate_map", "generate_taxonomy_map"].includes(row.type) &&
      row.state === "done",
  );

const startedAt = (row) => new Date(row.session.created_at).getTime();

/**
 * Sessions as {session, depth}, each grouped under the oldest ancestor still in
 * the list, oldest first. A fork of someone else's session has no ancestor here,
 * so it stands as its own root.
 */
export function family(sessions = []) {
  const byId = new Map(sessions.map((session) => [session.id, session]));
  const rootOf = (session) => {
    let depth = 0;
    let current = session;
    while (byId.has(current.forked_from_id) && depth < sessions.length) {
      current = byId.get(current.forked_from_id);
      depth += 1;
    }
    return [current.id, depth];
  };

  const groups = new Map();
  for (const session of sessions) {
    const [rootId, depth] = rootOf(session);
    groups.set(rootId, [...(groups.get(rootId) ?? []), { session, depth }]);
  }
  return [...groups.values()]
    .map((rows) => rows.sort((a, b) => startedAt(a) - startedAt(b)))
    .sort((a, b) => startedAt(b.at(-1)) - startedAt(a.at(-1)))
    .flat();
}

/** The step a session is currently sitting on, if any. */
export const activeStep = (rows) =>
  rows.find((row) => row.state === "ask") ??
  rows.find((row) => row.state === "failed") ??
  rows.find((row) => row.state === "running");

/** jsonb drops key order, so a trajectory is stored as [key, value] pairs. */
export const asTrajectory = (value) =>
  Array.isArray(value) ? Object.fromEntries(value) : (value ?? {});

/** What was chosen for a decision, by the labels it was offered under. */
export function answerLabels(decision) {
  const options = decision?.options ?? [];
  const named = (value) =>
    options.find((option) => JSON.stringify(option.value) === JSON.stringify(value))
      ?.label;
  return (decision?.answer ?? []).map(
    (value) =>
      named(value) ??
      value?.label ??
      value?.name ??
      value?.option ??
      value?.query ??
      JSON.stringify(value),
  );
}

/** What changed between a suggested artifact and the chosen one. */
export function diffChoice(suggested = [], chosen = [], key = JSON.stringify) {
  const suggestedKeys = suggested.map(key);
  const chosenKeys = chosen.map(key);
  return {
    kept: chosen.filter((item) => suggestedKeys.includes(key(item))),
    added: chosen.filter((item) => !suggestedKeys.includes(key(item))),
    removed: suggested.filter((item) => !chosenKeys.includes(key(item))),
  };
}

/* references ------------------------------------------------------------- */

export const STAGES = ["gathered", "included", "excluded", "mapped", "failed"];

/**
 * Screening's verdict on a reference.
 */
export function verdictOf(reference) {
  if (reference?.screening)
    return reference.screening.include ? "included" : "excluded";
  if (reference?.stage === "mapped") return "included";
  if (["included", "excluded", "failed"].includes(reference?.stage))
    return reference.stage;
  return "not screened";
}

/** Whether mapping has placed a reference yet. */
export const placementOf = (reference) =>
  reference?.stage === "mapped"
    ? "mapped"
    : reference?.stage === "failed"
      ? "failed"
      : "not mapped";

/**
 * How a view slices its references.
 */
export const SLICES = {
  stage: { label: "Stage", of: (reference) => reference.stage, order: STAGES },
  verdict: {
    label: "Screening",
    of: verdictOf,
    order: ["included", "excluded", "not screened", "failed"],
  },
  placement: {
    label: "Mapping",
    of: placementOf,
    order: ["mapped", "not mapped", "failed"],
  },
};

/** How many references sit in each of a slice's buckets. */
export const bucketCounts = (references = [], slice = SLICES.stage) =>
  slice.order
    .map((bucket) => ({
      bucket,
      count: references.filter((reference) => slice.of(reference) === bucket)
        .length,
    }))
    .filter((entry) => entry.count > 0);

const foundInMode = (mode) => (reference) =>
  (reference.provenance ?? []).some((entry) => entry.mode === mode);

const screenedIn = (reference) => verdictOf(reference) === "included";

export const REFERENCE_VIEWS = {
  retrieve_sparse_evidence: {
    subset: foundInMode("sparse"),
    slice: null,
    shows: ["found"],
  },
  retrieve_concept_evidence: {
    subset: foundInMode("taxonomy"),
    slice: null,
    shows: ["found"],
  },
  screen_evidence: { slice: SLICES.verdict, shows: ["screening", "found"] },
  generate_map: {
    subset: screenedIn,
    slice: SLICES.placement,
    shows: ["mapping", "coordinate"],
  },
  generate_taxonomy_map: {
    subset: screenedIn,
    slice: SLICES.placement,
    shows: ["mapping", "coordinate"],
  },
};

export const referenceStamp = (rows = []) =>
  rows
    .filter((row) => REFERENCE_VIEWS[row.type])
    .map(
      (row) =>
        `${row.type}:${row.state}:${row.operation?.progress?.done ?? ""}`,
    )
    .join(",");

/** The references a step's table shows, out of the session's, or null. */
export function referencesFor(type, references = null) {
  const view = REFERENCE_VIEWS[type];
  if (!view || !references) return null;
  return view.subset ? references.filter(view.subset) : references;
}

/**
 * A cell selection as dimension/subtopic pairs, all of which a reference's
 * coordinate has to satisfy.
 */
export const cellKey = (terms = []) =>
  terms
    .map(([dimension, subtopic]) => `${dimension}=${subtopic}`)
    .sort()
    .join("&");

export const inCell = (coordinate, terms = []) =>
  terms.every(([dimension, subtopic]) =>
    (coordinate?.[dimension] ?? []).includes(subtopic),
  );

export function filterReferences(
  references = [],
  filter = null,
  slice = SLICES.stage,
) {
  if (filter?.bucket && slice)
    return references.filter(
      (reference) => slice.of(reference) === filter.bucket,
    );
  if (filter?.terms)
    return references.filter((reference) =>
      inCell(reference.coordinate, filter.terms),
    );
  return references;
}

export function authorLine(evidence) {
  const authors = evidence?.authors ?? [];
  if (!authors.length) return "";
  return authors.length > 1 ? `${authors[0]} et al.` : authors[0];
}

/** A whole filter group, for when the reference's own concepts are unknown. */
const wholeGroup = ({ scheme, labels = [] }) =>
  scheme && labels.length
    ? `${scheme} · ${plural(labels.length, "concept")}`
    : (scheme ?? "");

/**
 * Which of a filter group's concepts this reference is annotated with. A group
 * is a whole-run set, but a reference came back for its own subset of it, and
 * `labels` and `concepts` are index-aligned (both are built by mapping over
 * concept_local_refs in generate_concept_filters).
 */
const matched = (group, known) =>
  (group?.concepts ?? []).flatMap((iri, index) =>
    known.has(iri) ? [group.labels?.[index] ?? iri] : [],
  );

/**
 * What found this reference, split by retrieval mode — a session can run both,
 * and a reference the two modes agree on is worth being able to see.
 *
 * `concepts` names the concepts the reference is actually annotated with out of
 * each filter group, which needs the concept_filters groups: they carry the IRIs
 * provenance does not record. Without them, or without hydrated evidence, it
 * falls back to naming the group as a whole.
 */
export function foundBy(reference, filterGroups = []) {
  const known = new Set(reference?.evidence?.known_concepts ?? []);
  const byScheme = new Map(filterGroups.map((group) => [group.scheme, group]));
  const queries = [];
  const concepts = [];

  for (const entry of reference?.provenance ?? []) {
    if (entry.mode !== "taxonomy") {
      if (entry.query) queries.push(entry.query);
      continue;
    }
    for (const filter of entry.filters ?? []) {
      const hits = known.size
        ? matched(byScheme.get(filter.scheme), known)
        : [];
      const label = hits.length
        ? `${filter.scheme}: ${hits.join(", ")}`
        : wholeGroup(filter);
      if (label) concepts.push(label);
    }
  }

  return { queries: [...new Set(queries)], concepts: [...new Set(concepts)] };
}

/**
 * A map payload as a grid. Any two dimensions can be the axes; the third
 * becomes the facet.
 */
export function buildGrid(map, { row = 0, col = 1, facet = null } = {}) {
  if (map?.dimensions?.length !== 3 || row === col) return null;
  const facetIndex = [0, 1, 2].find((index) => index !== row && index !== col);
  const rowDim = map.dimensions[row];
  const colDim = map.dimensions[col];
  const facetDim = map.dimensions[facetIndex];

  const within = (coordinate, dimension, name) =>
    (coordinate?.[dimension.name] ?? []).includes(name);
  const all = map.mapped_evidence ?? [];
  const evidence = all.filter(
    (item) => !facet || within(item.coordinate, facetDim, facet),
  );

  const names = (dimension) => [
    ...new Set(dimension.subtopics.map((s) => s.name)),
  ];
  const rows = names(rowDim);
  const cols = names(colDim);
  const cells = rows.map((name) =>
    cols.map(
      (other) =>
        evidence.filter(
          (item) =>
            within(item.coordinate, rowDim, name) &&
            within(item.coordinate, colDim, other),
        ).length,
    ),
  );

  return {
    rowDim,
    colDim,
    facetDim,
    rowIndex: row,
    colIndex: col,
    facetIndex,
    rows,
    cols,
    cells,
    maxCount: Math.max(0, ...cells.flat()),
    placed: evidence.length,
    total: all.length,
    facets: facetDim.subtopics.map((subtopic) => ({
      name: subtopic.name,
      count: all.filter((item) =>
        within(item.coordinate, facetDim, subtopic.name),
      ).length,
    })),
  };
}
