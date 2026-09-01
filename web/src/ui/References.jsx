import { useEffect, useRef, useState } from "preact/hooks";
import * as api from "../api.js";
import {
  authorLine,
  bucketCounts,
  filterReferences,
  foundBy,
  REFERENCE_VIEWS,
  referencesFor,
  SLICES,
} from "../derive.js";
import { usePoll } from "../poll.js";
import { referenceUrl } from "../repo.js";
import { External, Remove, Spinner } from "./Icons.jsx";
import { Reasoning } from "./Reasoning.jsx";
import { Toggle } from "./Panel.jsx";
import { Breakable } from "./text.jsx";

const REFRESH_MS = 5000;

const evidenceById = (rows) =>
  Object.fromEntries(rows.map((row) => [row.destiny_id, row.evidence ?? null]));

/**
 * The session's references, kept current while a step is still moving them.
 */
export function useReferences(
  sessionId,
  { enabled = true, live = false, stamp = "" } = {},
) {
  const [evidence, setEvidence] = useState({});
  const hydrating = useRef(false);

  const { data, error, loading } = usePoll(
    () => api.listReferences(sessionId),
    {
      interval: REFRESH_MS,
      active: () => live,
      deps: [sessionId, live, stamp],
      skip: !enabled,
    },
  );

  useEffect(() => setEvidence({}), [sessionId]);

  const missing = (data ?? [])
    .filter((reference) => evidence[reference.destiny_id] === undefined)
    .map((reference) => reference.destiny_id)
    .join(",");
  const hydrated = Boolean(Object.keys(evidence).length);

  useEffect(() => {
    if (!missing || hydrating.current) return;
    hydrating.current = true;
    const merge = (rows) =>
      setEvidence((previous) => ({ ...previous, ...evidenceById(rows) }));
    api
      .listReferences(sessionId, { includeEvidence: true })
      .then(merge, () => merge(data ?? []))
      .finally(() => {
        hydrating.current = false;
      });
  }, [sessionId, missing]);

  return {
    references:
      data?.map((reference) => ({
        ...reference,
        evidence: evidence[reference.destiny_id] ?? null,
      })) ?? null,
    error,
    loading: loading || (Boolean(missing) && !hydrated),
  };
}

const Filter = ({ label, count, on, onClick }) => (
  <button type="button" class={`facet ${on ? "on" : ""}`} onClick={onClick}>
    <span>{label}</span>
    <span class="facet-n">{count}</span>
  </button>
);

const Chips = ({ label, children }) => (
  <div class="ref-why-part">
    <div class="lab">{label}</div>
    <div class="chips" style="margin-top: 5px;">
      {children}
    </div>
  </div>
);

/** Why this reference is where it is, as far as the view being read goes. */
export function Why({ reference, filterGroups, shows = null }) {
  const has = (part) => !shows || shows.includes(part);
  const found = has("found") ? foundBy(reference, filterGroups) : null;
  const coordinate = has("coordinate")
    ? Object.entries(reference.coordinate ?? {})
    : [];
  return (
    <div class="ref-why">
      {has("screening") ? (
        <Reasoning
          label={`Model reasoning: ${
            reference.screening?.include ? "inclusion" : "exclusion"
          }`}
          text={reference.screening?.reasoning}
        />
      ) : null}
      {has("mapping") ? (
        <Reasoning
          label="Model reasoning: mapping"
          text={reference.mapping?.reasoning}
        />
      ) : null}
      {coordinate.length ? (
        <div class="ref-why-part">
          <div class="lab">Coordinate</div>
          {coordinate.map(([dimension, subtopics]) => (
            <div class="ref-axis" key={dimension}>
              <div class="ref-axis-name">
                <Breakable>{dimension}</Breakable>
              </div>
              <div class="chips">
                {subtopics.map((subtopic) => (
                  <span class="chip" key={subtopic}>
                    <Breakable>{subtopic}</Breakable>
                  </span>
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : null}
      {found?.queries.length ? (
        <Chips label="Found by search query">
          {found.queries.map((query) => (
            <span class="chip" key={query}>
              {query}
            </span>
          ))}
        </Chips>
      ) : null}
      {found?.concepts.length ? (
        <Chips label="Found by taxonomy concept">
          {found.concepts.map((label) => (
            <span class="chip" key={label}>
              <Breakable>{label}</Breakable>
            </span>
          ))}
        </Chips>
      ) : null}
      <div class="ref-why-part">
        <div class="lab">Repository id</div>
        <div class="ref-why-id mono">{reference.destiny_id}</div>
        {!reference.evidence ? (
          <div class="ref-why-text">
            The repository returned no record for this id, so it has no title or
            authors to show.
          </div>
        ) : null}
      </div>
    </div>
  );
}

const slug = (bucket) => bucket.replace(/ /g, "-");

function Row({ reference, community, filterGroups, slice, shows }) {
  const [open, setOpen] = useState(false);
  const { evidence } = reference;
  const meta = [authorLine(evidence), evidence?.year]
    .filter(Boolean)
    .join(" · ");
  const bucket = slice ? slice.of(reference) : null;
  return (
    <>
      <div class={`ref-row ${open ? "open" : ""}`}>
        <button
          type="button"
          class="ref-main"
          onClick={() => setOpen(!open)}
          aria-expanded={open}
        >
          <span class="ref-text">
            <span class="ref-title">
              {evidence?.title ?? "Untitled reference"}
            </span>
            {meta ? <span class="ref-meta">{meta}</span> : null}
          </span>
          {bucket ? (
            <span class={`ref-stage ${slug(bucket)}`}>{bucket}</span>
          ) : null}
          <Toggle open={open} />
        </button>
        <a
          class="ref-link"
          href={referenceUrl(community, reference.destiny_id)}
          target="_blank"
          rel="noreferrer"
          title="Open in the evidence repository"
        >
          <External colour="#6f6b63" />
        </a>
      </div>
      {open ? (
        <Why reference={reference} filterGroups={filterGroups} shows={shows} />
      ) : null}
    </>
  );
}

export function References({
  references,
  community,
  filterGroups,
  cell,
  onClearCell,
  loading,
  error,
  slice = SLICES.stage,
  shows = null,
  inset = false,
}) {
  const [bucket, setBucket] = useState(null);
  const anchor = useRef(null);

  useEffect(() => {
    if (!cell) return;
    setBucket(null);
    anchor.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [cell?.key]);

  useEffect(() => setBucket(null), [slice]);

  const pickBucket = (next) => {
    onClearCell?.();
    setBucket(next);
  };

  const classes = `refs ${inset ? "inset" : ""}`;
  const heading = <div class={inset ? "lab" : "map-title"}>References</div>;
  const head = (
    <div class="refs-head" ref={anchor}>
      {heading}
    </div>
  );

  if (loading)
    return (
      <section class={classes}>
        {head}
        <div class="note" style="display: flex; align-items: center; gap: 9px;">
          <Spinner /> Fetching references...
        </div>
      </section>
    );

  if (error)
    return (
      <section class={classes}>
        {head}
        <div class="error">{String(error.message ?? error)}</div>
      </section>
    );

  if (!references?.length)
    return (
      <section class={classes}>
        {head}
        <div class="note">This session has no references.</div>
      </section>
    );

  const counts = slice ? bucketCounts(references, slice) : [];
  const shown = filterReferences(
    references,
    cell ?? (bucket ? { bucket } : null),
    slice,
  );
  return (
    <section class={classes}>
      <div class="refs-head" ref={anchor}>
        {heading}
        <div class="refs-count">
          {shown.length === references.length
            ? `All ${references.length}.`
            : `${shown.length} of ${references.length}.`}
        </div>
      </div>

      {slice || cell ? (
        <div class="map-controls">
          {slice ? (
            <div class="facets">
              <span class="lab">{slice.label}</span>
              <Filter
                label="All"
                count={references.length}
                on={!bucket && !cell}
                onClick={() => pickBucket(null)}
              />
              {counts.map((entry) => (
                <Filter
                  key={entry.bucket}
                  label={entry.bucket}
                  count={entry.count}
                  on={bucket === entry.bucket}
                  onClick={() =>
                    pickBucket(bucket === entry.bucket ? null : entry.bucket)
                  }
                />
              ))}
            </div>
          ) : null}
          {cell ? (
            <button type="button" class="cell-chip" onClick={onClearCell}>
              <span>{cell.label}</span>
              <Remove />
            </button>
          ) : null}
        </div>
      ) : null}

      <div class="ref-list">
        {shown.length ? (
          shown.map((reference) => (
            <Row
              key={reference.destiny_id}
              reference={reference}
              community={community}
              filterGroups={filterGroups}
              slice={slice}
              shows={shows}
            />
          ))
        ) : (
          <div class="note">Nothing matches this filter.</div>
        )}
      </div>
    </section>
  );
}

/**
 * A step's own slice of the table.
 */
export function stepReferences(type, refs) {
  const view = REFERENCE_VIEWS[type];
  if (!view || !refs) return null;
  const shown = referencesFor(type, refs.references);
  // Loading says the table is coming; nothing in it once loaded says the step
  // has none, which is the step's own business to report.
  if (!refs.loading && !refs.error && !shown?.length) return null;
  return (
    <References
      inset
      slice={view.slice}
      shows={view.shows}
      references={shown}
      community={refs.community}
      filterGroups={refs.filterGroups}
      loading={refs.loading}
      error={refs.error}
    />
  );
}
