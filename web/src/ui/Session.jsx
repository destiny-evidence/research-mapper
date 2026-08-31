import { useEffect, useRef, useState } from "preact/hooks";
import * as api from "../api.js";
import { MAP_TAILS } from "../plan.js";
import {
  steps,
  activeStep,
  hasCounts,
  mapIsReady,
  nextToStart,
  progressText,
} from "../derive.js";
import { downloadRecord } from "../record.js";
import { usePoll } from "../poll.js";
import { Panel, Toggle, Pip } from "./Panel.jsx";
import { Question } from "./Ask.jsx";
import { Trace } from "./Trace.jsx";
import { EvidenceMap } from "./EvidenceMap.jsx";
import {
  Artifact,
  RENDERERS,
  ARTIFACT_FOR_STEP,
  SUGGESTION_FOR_STEP,
  WANTED,
} from "./artifacts/index.jsx";
import { Reasoning } from "./Reasoning.jsx";
import { Download } from "./Icons.jsx";
import { Scope } from "./Scope.jsx";

const MOVING = new Set(["pending", "running"]);

async function load(id) {
  const [session, operationIds] = await Promise.all([
    api.getSession(id),
    api.listOperationIds(id),
  ]);
  // Each operation carries its own open questions and answered decisions.
  const operations = await Promise.all(operationIds.map(api.getOperation));
  return { session, operations };
}

/** Artifacts we can render, fetched once per version and cached. */
function useArtifacts(sessionId, versions = {}) {
  const [cache, setCache] = useState({});
  const wanted = Object.keys(versions).filter((type) => WANTED.has(type));
  const stamp = wanted.map((type) => `${type}@${versions[type]}`).join(",");

  useEffect(() => {
    let live = true;
    const missing = wanted.filter(
      (type) => cache[`${type}@${versions[type]}`] === undefined,
    );
    if (!missing.length) return;
    Promise.all(
      missing.map((type) =>
        api.getArtifact(sessionId, type).then(
          (artifact) => [`${type}@${versions[type]}`, artifact.payload],
          () => [`${type}@${versions[type]}`, null],
        ),
      ),
    ).then(
      (entries) =>
        live &&
        setCache((previous) => ({
          ...previous,
          ...Object.fromEntries(entries),
        })),
    );
    return () => {
      live = false;
    };
  }, [sessionId, stamp]);

  return (type) => cache[`${type}@${versions[type]}`] ?? null;
}

export function Session({ id }) {
  const { data, error, refresh } = usePoll(() => load(id), {
    active: ({ operations }) =>
      operations.some((operation) => MOVING.has(operation.status)),
    deps: [id],
  });
  const [overrides, setOverrides] = useState({});
  const [saving, setSaving] = useState(false);
  const [map, setMap] = useState(null);
  const [workflowOpen, setWorkflowOpen] = useState(false);
  const started = useRef(new Set());
  const [problem, setProblem] = useState(null);

  const session = data?.session;
  const artifact = useArtifacts(id, session?.artifacts);
  const rows = data ? steps(data) : [];
  const mapped = mapIsReady(rows);

  useEffect(() => {
    // The view needs coordinates, not the references themselves.
    if (mapped)
      api
        .getMap(id, { includeEvidence: false })
        .then(setMap, () => setMap(null));
  }, [id, mapped]);

  // Keep the session moving: see nextToStart.
  useEffect(() => {
    if (!data) return;
    const next = nextToStart(rows);
    if (!next || started.current.has(next)) return;
    started.current.add(next);
    setProblem(null);
    api.startOperation(id, next).then(refresh, (failure) => {
      started.current.delete(next);
      setProblem(`Could not start ${next}: ${failure.message}`);
    });
  }, [data]);

  if (error && !data)
    return (
      <div class="page">
        <div class="error">{String(error.message)}</div>
      </div>
    );
  if (!data)
    return (
      <div class="page">
        <div class="note">Loading…</div>
      </div>
    );

  const active = activeStep(rows);
  const isOpen = (row) => overrides[row.type] ?? row === active;
  const toggle = (row) =>
    setOverrides({ ...overrides, [row.type]: !isOpen(row) });

  const answer = async (operationId, key, value) => {
    setSaving(true);
    try {
      await api.respond(operationId, { [key]: value });
      refresh();
    } finally {
      setSaving(false);
    }
  };

  const retryStep = async (operationId) => {
    await api.retry(operationId);
    refresh();
  };

  // Starting a step by hand
  const startStep = async (type) => {
    started.current.add(type);
    await api.startOperation(id, type);
    refresh();
  };

  const included = rows.find((row) => row.type === "screen_evidence")?.operation
    ?.result?.included;

  const stepList = rows.map((row) => (
    <Panel
      key={row.type}
      state={row.state}
      title={row.title}
      summary={row.summary}
      open={isOpen(row)}
      onToggle={() => toggle(row)}
    >
      <Body
        row={row}
        artifact={artifact}
        onAnswer={answer}
        onRetry={retryStep}
        onStart={startStep}
        saving={saving}
      />
    </Panel>
  ));

  return (
    <div class="page">
      <div class="session-head">
        <div class="grow">
          <div class="question">{session.question}</div>
          <div class="meta">
            {session.community.toUpperCase()} ·{" "}
            {new Date(session.created_at).toLocaleString()}
          </div>
          <Scope community={session.community} />
        </div>
        <button class="quiet" onClick={() => downloadRecord(id)}>
          <Download /> Full record
        </button>
      </div>

      {problem ? (
        <div class="error" style="margin-bottom: 16px;">
          {problem}
        </div>
      ) : null}

      {map ? (
        <>
          <div
            class={`workflow ${workflowOpen ? "" : "closed"}`}
            style="margin-top: 22px;"
          >
            <button
              type="button"
              class="workflow-head"
              onClick={() => setWorkflowOpen(!workflowOpen)}
            >
              <Pip state="done" />
              <span style="font-size: 13px; color: var(--ink); font-weight: 500;">
                Workflow
              </span>
              <span class="step-summary">{overview(rows)}</span>
              <Toggle open={workflowOpen} />
            </button>
            {workflowOpen ? <div class="workflow-steps">{stepList}</div> : null}
          </div>
          <EvidenceMap
            map={map}
            included={included}
            community={session.community}
          />
        </>
      ) : (
        stepList
      )}
    </div>
  );
}

const overview = (rows) =>
  `${rows.filter((row) => row.state === "done").length} steps`;

const PROBLEM = new Set(["failed", "dropped", "errors", "skipped"]);

/** A step's own result, used when no artifact exists. */
function Result({ result }) {
  const entries = Object.entries(result ?? {}).filter(
    ([key]) => key !== "version",
  );
  if (!entries.length) return null;
  const ordered = [
    ...entries.filter(([key]) => !PROBLEM.has(key)),
    ...entries.filter(([key]) => PROBLEM.has(key)),
  ];
  return (
    <div class="counts">
      {ordered.map(([key, value]) => (
        <div key={key} class={PROBLEM.has(key) ? "bad" : undefined}>
          <div class="lab">{key.replace(/_/g, " ")}</div>
          <div class="n">{value}</div>
        </div>
      ))}
    </div>
  );
}

/** What a step shows when it is open. */
export function Body({
  row,
  artifact,
  onAnswer,
  onRetry = () => {},
  onStart = () => {},
  saving,
}) {
  if (row.state === "failed") {
    const other = Object.values(MAP_TAILS).find(
      (tail) =>
        tail.head !== row.type &&
        Object.values(MAP_TAILS).some((t) => t.head === row.type),
    );
    return (
      <>
        <div class="error">
          {row.operation.error?.message ?? JSON.stringify(row.operation.error)}
        </div>
        <div class="actions">
          <button class="btn" onClick={() => onRetry(row.operation.id)}>
            Retry
          </button>
          {other ? (
            <button class="btn plain" onClick={() => onStart(other.head)}>
              {other.label}
            </button>
          ) : null}
        </div>
      </>
    );
  }

  if (row.branch) {
    return (
      <div class="choices">
        {Object.entries(row.branch).map(([key, tail]) => (
          <button
            type="button"
            class="choice"
            key={key}
            onClick={() => onStart(tail.head)}
          >
            <span class="choice-label">{tail.label}</span>
            <span class="choice-detail">{tail.detail}</span>
          </button>
        ))}
      </div>
    );
  }

  if (row.state === "ask") {
    const suggestion = artifact(SUGGESTION_FOR_STEP[row.type]);
    return (
      <>
        {row.questions.map((decision) => (
          <Question
            key={decision.id}
            decision={decision}
            saving={saving}
            onAnswer={(value) =>
              onAnswer(row.operation.id, decision.key, value)
            }
          />
        ))}
        {row.questions.length > 1 ? (
          <div class="hint" style="margin-top: 12px;">
            {row.operation.decisions.filter((d) => d.answer != null).length} of{" "}
            {row.operation.decisions.length} saved
          </div>
        ) : null}
        {row.type === "generate_concept_filters" ? (
          <Trace payload={artifact("concept_filter_loop")} />
        ) : null}
        <Reasoning text={suggestion?.reasoning} />
      </>
    );
  }

  if (row.state === "running") {
    const { progress } = row.operation;
    const counted = hasCounts(progress);
    return (
      <>
        <div class={counted ? "bar" : "bar working"}>
          <div
            style={
              counted
                ? `width: ${Math.round((100 * progress.done) / progress.total)}%;`
                : ""
            }
          />
        </div>
        <div class="note" style="margin-top: 11px;">
          {row.operation.status === "pending"
            ? "Queued"
            : progressText(progress)}
        </div>
      </>
    );
  }

  const type = ARTIFACT_FOR_STEP[row.type];
  const payload = type ? artifact(type) : null;
  const suggestion = artifact(SUGGESTION_FOR_STEP[row.type]);
  const result = row.operation?.result;

  const reasoning = payload?.reasoning || suggestion?.reasoning;
  const trace =
    row.type === "generate_concept_filters"
      ? artifact("concept_filter_loop")
      : null;

  if (!payload && !result && !reasoning && !trace) {
    return <div class="note">Nothing to show for this step.</div>;
  }
  return (
    <>
      {payload ? (
        <Artifact
          type={type}
          payload={payload}
          suggested={artifact(RENDERERS[type]?.suggests)}
        />
      ) : (
        <Result result={result} />
      )}
      {trace ? <Trace payload={trace} /> : null}
      <Reasoning text={reasoning} />
    </>
  );
}
