import { useEffect, useRef, useState } from "preact/hooks";
import * as api from "../api.js";
import {
  authorLine,
  decisionLabel,
  foundBy,
  REFERENCE_VIEWS,
  unplacedBecause,
  VIEW_SLICES,
} from "../derive.js";
import { usePoll } from "../poll.js";
import { referenceUrl } from "../repo.js";
import { External, Remove, Spinner } from "./Icons.jsx";
import { Reasoning } from "./Reasoning.jsx";
import { Toggle } from "./Panel.jsx";
import { Breakable } from "./text.jsx";

export const PAGE_SIZE = 50;

/**
 * Paging through a stack of cursors: each entry is the `after` its page was
 * fetched with, so Previous pops one and Next pushes the page's `next`. A new
 * view, bucket or cell starts again from the first page.
 */
export function pager(stack, page, limit = PAGE_SIZE) {
  return {
    start: (stack.length - 1) * limit,
    hasPrevious: stack.length > 1,
    hasNext: Boolean(page?.next),
    forward: () => (page?.next ? [...stack, page.next] : stack),
    back: () => (stack.length > 1 ? stack.slice(0, -1) : stack),
  };
}

/**
 * One page of a view's references, with the page's own evidence. It refetches
 * the page it is on when `stamp` changes, which is while a step is moving
 * references between buckets.
 */
export function useReferencePage(
  sessionId,
  { view = "all", bucket = null, cell = null, stamp = "", enabled = true } = {},
) {
  const key = JSON.stringify([sessionId, view, bucket, cell?.key ?? null]);
  const [cursors, setCursors] = useState({ key, stack: [null] });
  const stack = cursors.key === key ? cursors.stack : [null];
  const after = stack[stack.length - 1];

  const { data, error, loading } = usePoll(
    () =>
      api
        .listReferences(sessionId, {
          view,
          bucket,
          cell: cell?.terms,
          after,
          limit: PAGE_SIZE,
          includeEvidence: true,
        })
        .then((page) => ({ ...page, request: `${key}|${after}` })),
    { active: () => false, deps: [key, after, stamp], skip: !enabled },
  );

  // Until the page asked for arrives, the last one is kept for its counts and
  // buckets, but `pending` says its rows are stale: "page" when moving through
  // the same view, "filter" when the bucket or cell changed. Its `next` belongs
  // to another page, so it can't move anything. A refetch of the same page (a
  // new `stamp`) isn't pending, so a running step doesn't flicker the rows.
  const current = data?.request === `${key}|${after}` ? data : null;
  const pending =
    data && !current
      ? data.request.startsWith(`${key}|`)
        ? "page"
        : "filter"
      : null;
  const paging = pager(stack, current);
  return {
    page: data,
    pending,
    error,
    loading: loading && !data,
    ...paging,
    next: () => setCursors({ key, stack: paging.forward() }),
    previous: () => setCursors({ key, stack: paging.back() }),
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
export function Why({ reference, filterGroups, shows = null, reason = null }) {
  const has = (part) => !shows || shows.includes(part);
  const unplaced = reason?.(reference) ?? null;
  const found = has("found") ? foundBy(reference, filterGroups) : null;
  const coordinate = has("coordinate")
    ? Object.entries(reference.coordinate ?? {})
    : [];
  const by = (decision) =>
    decision?.model ? ` · ${decisionLabel(decision, { short: true })}` : "";
  return (
    <div class="ref-why">
      {has("screening") ? (
        <Reasoning
          label={`Model reasoning: ${
            reference.screening?.include ? "inclusion" : "exclusion"
          }${by(reference.screening)}`}
          text={reference.screening?.reasoning}
        />
      ) : null}
      {has("mapping") ? (
        <Reasoning
          label={`Model reasoning: mapping${by(reference.mapping)}`}
          text={reference.mapping?.reasoning}
        />
      ) : null}
      {unplaced ? (
        <div class="ref-why-part">
          <div class="lab">Not on the map</div>
          <div class="ref-why-text">{unplaced}</div>
        </div>
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

function Row({ reference, community, filterGroups, slice, shows, reason }) {
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
        <Why
          reference={reference}
          filterGroups={filterGroups}
          shows={shows}
          reason={reason}
        />
      ) : null}
    </>
  );
}

const fmt = new Intl.NumberFormat();

/**
 * "All 42.", "12 of 42." or, across pages, "51–100 of 4,210." While a page is
 * `pending`, its range is the one asked for, as far as the last page's counts
 * tell; while a new filter is, there is nothing to count yet.
 */
export function countText(
  page,
  { start = 0, hasNext = false, pending = null, limit = PAGE_SIZE } = {},
) {
  if (pending === "filter") return "Fetching references...";
  const shown =
    pending === "page"
      ? Math.max(0, Math.min(limit, page.matched - start))
      : page.items.length;
  if (!start && !hasNext)
    return shown === page.total
      ? `All ${fmt.format(page.total)}.`
      : `${fmt.format(page.matched)} of ${fmt.format(page.total)}.`;
  return `${fmt.format(start + 1)}–${fmt.format(start + shown)} of ${fmt.format(page.matched)}.`;
}

/**
 * A page of references as a table: its buckets, which models decided it, the
 * rows, and the controls to move between pages. Everything it shows comes in
 * on `page`, so it renders the same however big the session is.
 */
export function ReferenceTable({
  page,
  pending = null,
  loading = false,
  error = null,
  view = "all",
  community,
  filterGroups,
  bucket = null,
  onBucket = () => {},
  cell = null,
  onClearCell,
  shows = null,
  reason = null,
  inset = false,
  anchor = null,
  start = 0,
  hasPrevious = false,
  hasNext = false,
  onPrevious = () => {},
  onNext = () => {},
}) {
  const classes = `refs ${inset ? "inset" : ""}`;
  const heading = <div class={inset ? "lab" : "map-title"}>References</div>;

  if (!page && loading)
    return (
      <section class={classes}>
        <div class="refs-head" ref={anchor}>
          {heading}
        </div>
        <div class="note" style="display: flex; align-items: center; gap: 9px;">
          <Spinner /> Fetching references...
        </div>
      </section>
    );

  if (!page && error)
    return (
      <section class={classes}>
        <div class="refs-head" ref={anchor}>
          {heading}
        </div>
        <div class="error">{String(error.message ?? error)}</div>
      </section>
    );

  if (!page?.total)
    return (
      <section class={classes}>
        <div class="refs-head" ref={anchor}>
          {heading}
        </div>
        <div class="note">This session has no references.</div>
      </section>
    );

  const slice = VIEW_SLICES[view] ?? null;
  return (
    <section class={classes}>
      <div class="refs-head" ref={anchor}>
        {heading}
        <div class="refs-count">{countText(page, { start, hasNext, pending })}</div>
        {(page.decided ?? []).map((decision) => (
          <div
            class={`refs-decided ${decision.dedicated === false ? "fallback" : ""}`}
            key={`${decision.model}|${decision.dedicated}`}
          >
            Decided by {decisionLabel(decision)}
          </div>
        ))}
      </div>

      {slice || cell ? (
        <div class="map-controls">
          {slice ? (
            <div class="facets">
              <span class="lab">{slice.label}</span>
              <Filter
                label="All"
                count={page.total}
                on={!bucket && !cell}
                onClick={() => onBucket(null)}
              />
              {(page.buckets ?? []).map((entry) => (
                <Filter
                  key={entry.bucket}
                  label={entry.bucket}
                  count={entry.count}
                  on={bucket === entry.bucket}
                  onClick={() =>
                    onBucket(bucket === entry.bucket ? null : entry.bucket)
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
        {pending ? (
          error ? (
            <div class="error">{String(error.message ?? error)}</div>
          ) : (
            <div
              class="note"
              style="display: flex; align-items: center; gap: 9px;"
            >
              <Spinner /> Fetching references...
            </div>
          )
        ) : page.items.length ? (
          page.items.map((reference) => (
            <Row
              key={reference.destiny_id}
              reference={reference}
              community={community}
              filterGroups={filterGroups}
              slice={slice}
              shows={shows}
              reason={reason}
            />
          ))
        ) : (
          <div class="note">Nothing matches this filter.</div>
        )}
      </div>

      {hasPrevious || hasNext || pending === "page" ? (
        <div class="pager">
          <button
            type="button"
            class="btn plain"
            disabled={!hasPrevious}
            onClick={onPrevious}
          >
            ‹ Previous
          </button>
          <button
            type="button"
            class="btn plain"
            disabled={!hasNext}
            onClick={onNext}
          >
            Next ›
          </button>
        </div>
      ) : null}
    </section>
  );
}

/**
 * A view's references, a page at a time. `hideEmpty` renders nothing once the
 * view turns out to have no references, for a step that has none to show.
 */
export function References({
  sessionId,
  view = "all",
  community,
  filterGroups,
  cell = null,
  onClearCell,
  shows = null,
  reason = null,
  inset = false,
  stamp = "",
  enabled = true,
  hideEmpty = false,
}) {
  const [bucket, setBucket] = useState(null);
  const anchor = useRef(null);

  useEffect(() => {
    if (!cell) return;
    setBucket(null);
    anchor.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [cell?.key]);

  useEffect(() => setBucket(null), [view]);

  const paging = useReferencePage(sessionId, {
    view,
    bucket: cell ? null : bucket,
    cell,
    stamp,
    enabled,
  });

  if (hideEmpty && paging.page && !paging.page.total) return null;

  // The rows give way to a spinner on a page turn, so bring the table's head
  // back into view rather than leave the reader below a shorter list.
  const turn = (move) => () => {
    move();
    anchor.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  };

  return (
    <ReferenceTable
      page={paging.page}
      pending={paging.pending}
      loading={paging.loading}
      error={paging.error}
      view={view}
      community={community}
      filterGroups={filterGroups}
      bucket={bucket}
      onBucket={(next) => {
        onClearCell?.();
        setBucket(next);
      }}
      cell={cell}
      onClearCell={onClearCell}
      shows={shows}
      reason={reason}
      inset={inset}
      anchor={anchor}
      start={paging.start}
      hasPrevious={paging.hasPrevious}
      hasNext={paging.hasNext}
      onPrevious={turn(paging.previous)}
      onNext={turn(paging.next)}
    />
  );
}

/**
 * A step's own table of references, or null for a step that has none.
 * `refs` carries what every table shares: the session, its community and
 * concept filters, and when to refetch.
 */
export function stepReferences(type, refs, state = "done") {
  const view = REFERENCE_VIEWS[type];
  if (!view || !refs) return null;
  return (
    <References
      inset
      hideEmpty
      sessionId={refs.sessionId}
      view={view.view}
      shows={view.shows}
      reason={
        view.tail && state === "done"
          ? (reference) => unplacedBecause(reference, view.tail)
          : null
      }
      community={refs.community}
      filterGroups={refs.filterGroups}
      stamp={refs.stamp}
      enabled={refs.enabled}
    />
  );
}
