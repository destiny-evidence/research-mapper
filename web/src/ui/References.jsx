import { useEffect, useRef, useState } from "preact/hooks";
import * as api from "../api.js";
import {
  authorLine,
  filterReferences,
  foundBy,
  stageCounts,
} from "../derive.js";
import { referenceUrl } from "../repo.js";
import { Chevron, External, Remove, Spinner } from "./Icons.jsx";
import { Reasoning } from "./Reasoning.jsx";
import { Breakable } from "./text.jsx";

export function useReferences(sessionId, enabled) {
  const [state, setState] = useState({ references: null, error: null });

  useEffect(() => {
    if (!enabled) return;
    let live = true;
    setState({ references: null, error: null });
    api.listReferences(sessionId, { includeEvidence: true }).then(
      (references) => live && setState({ references, error: null }),
      (error) => live && setState({ references: null, error }),
    );
    return () => {
      live = false;
    };
  }, [sessionId, enabled]);

  return { ...state, loading: !state.references && !state.error };
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

/** Why this reference is where it is. */
function Why({ reference, filterGroups }) {
  const found = foundBy(reference, filterGroups);
  const coordinate = Object.entries(reference.coordinate ?? {});
  return (
    <div class="ref-why">
      <Reasoning
        label={`Model reasoning: ${
          reference.screening?.include ? "inclusion" : "exclusion"
        }`}
        text={reference.screening?.reasoning}
      />
      <Reasoning
        label="Model reasoning: mapping"
        text={reference.mapping?.reasoning}
      />
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
      {found.queries.length ? (
        <Chips label="Found by search query">
          {found.queries.map((query) => (
            <span class="chip" key={query}>
              {query}
            </span>
          ))}
        </Chips>
      ) : null}
      {found.concepts.length ? (
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

function Row({ reference, community, filterGroups }) {
  const [open, setOpen] = useState(false);
  const { evidence } = reference;
  const meta = [authorLine(evidence), evidence?.year]
    .filter(Boolean)
    .join(" · ");
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
          <span class={`ref-stage ${reference.stage}`}>{reference.stage}</span>
          <Chevron up={open} size={12} colour="#6f6b63" />
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
      {open ? <Why reference={reference} filterGroups={filterGroups} /> : null}
    </>
  );
}

/** Every reference the session touched. */
export function References({
  references,
  community,
  filterGroups,
  cell,
  onClearCell,
  loading,
  error,
}) {
  const [stage, setStage] = useState(null);
  const anchor = useRef(null);

  useEffect(() => {
    if (!cell) return;
    setStage(null);
    anchor.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [cell?.key]);

  const pickStage = (next) => {
    onClearCell?.();
    setStage(next);
  };

  const head = (
    <div class="refs-head" ref={anchor}>
      <div class="map-title">References</div>
    </div>
  );

  if (loading)
    return (
      <section class="refs">
        {head}
        <div class="note" style="display: flex; align-items: center; gap: 9px;">
          <Spinner /> Fetching references...
        </div>
      </section>
    );

  if (error)
    return (
      <section class="refs">
        {head}
        <div class="error">{String(error.message ?? error)}</div>
      </section>
    );

  if (!references?.length)
    return (
      <section class="refs">
        {head}
        <div class="note">This session has no references.</div>
      </section>
    );

  const counts = stageCounts(references);
  const shown = filterReferences(
    references,
    cell ?? (stage ? { stage } : null),
  );
  return (
    <section class="refs">
      <div class="refs-head" ref={anchor}>
        <div class="map-title">References</div>
        <div style="font-size: 12px; color: var(--muted); margin-top: 5px;">
          {shown.length === references.length
            ? `All ${references.length}.`
            : `${shown.length} of ${references.length}.`}
        </div>
      </div>

      <div class="map-controls">
        <div class="facets">
          <span class="lab">Stage</span>
          <Filter
            label="All"
            count={references.length}
            on={!stage && !cell}
            onClick={() => pickStage(null)}
          />
          {counts.map((entry) => (
            <Filter
              key={entry.stage}
              label={entry.stage}
              count={entry.count}
              on={stage === entry.stage}
              onClick={() =>
                pickStage(stage === entry.stage ? null : entry.stage)
              }
            />
          ))}
        </div>
        {cell ? (
          <button type="button" class="cell-chip" onClick={onClearCell}>
            <span>{cell.label}</span>
            <Remove />
          </button>
        ) : null}
      </div>

      <div class="ref-list">
        {shown.length ? (
          shown.map((reference) => (
            <Row
              key={reference.destiny_id}
              reference={reference}
              community={community}
              filterGroups={filterGroups}
            />
          ))
        ) : (
          <div class="note">Nothing matches this filter.</div>
        )}
      </div>
    </section>
  );
}
