import { useEffect, useState } from 'preact/hooks'
import * as api from '../api.js'
import { steps, activeStep, progressText } from '../derive.js'
import { downloadRecord } from '../record.js'
import { usePoll } from '../poll.js'
import { Panel, Toggle, Pip } from './Panel.jsx'
import { Question } from './Ask.jsx'
import { Trace } from './Trace.jsx'
import { EvidenceMap } from './EvidenceMap.jsx'
import { Artifact, RENDERERS, ARTIFACT_FOR_STEP } from './artifacts/index.jsx'
import { Download } from './Icons.jsx'

const MOVING = new Set(['pending', 'running'])

async function load(id) {
  const [session, operationIds, decisions] = await Promise.all([
    api.getSession(id),
    api.listOperationIds(id),
    api.listDecisions(id),
  ])
  const operations = await Promise.all(operationIds.map(api.getOperation))
  return { session, operations, decisions }
}

/** Artifacts we can render, fetched once per version and cached. */
function useArtifacts(sessionId, versions = {}) {
  const [cache, setCache] = useState({})
  const wanted = Object.keys(versions).filter(
    (type) => RENDERERS[type] || Object.values(RENDERERS).some((entry) => entry.suggests === type) || type === 'concept_filter_loop',
  )
  const stamp = wanted.map((type) => `${type}@${versions[type]}`).join(',')

  useEffect(() => {
    let live = true
    const missing = wanted.filter((type) => cache[`${type}@${versions[type]}`] === undefined)
    if (!missing.length) return
    Promise.all(
      missing.map((type) =>
        api.getArtifact(sessionId, type).then(
          (artifact) => [`${type}@${versions[type]}`, artifact.payload],
          () => [`${type}@${versions[type]}`, null],
        ),
      ),
    ).then((entries) => live && setCache((previous) => ({ ...previous, ...Object.fromEntries(entries) })))
    return () => {
      live = false
    }
  }, [sessionId, stamp])

  return (type) => cache[`${type}@${versions[type]}`] ?? null
}

export function Session({ id, onBack }) {
  const { data, error, refresh } = usePoll(() => load(id), {
    active: ({ operations }) => operations.some((operation) => MOVING.has(operation.status)),
    deps: [id],
  })
  const [overrides, setOverrides] = useState({})
  const [saving, setSaving] = useState(false)
  const [map, setMap] = useState(null)
  const [workflowOpen, setWorkflowOpen] = useState(false)

  const session = data?.session
  const artifact = useArtifacts(id, session?.artifacts)
  const rows = data ? steps(data) : []
  const mapped = rows.find((row) => row.type === 'generate_map')?.state === 'done'

  useEffect(() => {
    if (mapped) api.getMap(id).then(setMap, () => setMap(null))
  }, [id, mapped])

  if (error && !data) return <div class="page"><div class="error">{String(error.message)}</div></div>
  if (!data) return <div class="page"><div class="note">Loading…</div></div>

  const active = activeStep(rows)
  const isOpen = (row) => overrides[row.type] ?? row === active
  const toggle = (row) => setOverrides({ ...overrides, [row.type]: !isOpen(row) })

  const answer = async (operationId, key, value) => {
    setSaving(true)
    try {
      await api.respond(operationId, { [key]: value })
      refresh()
    } finally {
      setSaving(false)
    }
  }

  const retryStep = async (operationId) => {
    await api.retry(operationId)
    refresh()
  }

  const included = rows.find((row) => row.type === 'screen_evidence')?.operation?.result?.included

  const stepList = rows.map((row) => (
    <Panel
      key={row.type}
      state={row.state}
      title={row.title}
      summary={row.summary || (row.state === 'todo' ? hintFor(row) : '')}
      open={isOpen(row)}
      onToggle={() => toggle(row)}
    >
      <Body row={row} artifact={artifact} onAnswer={answer} onRetry={retryStep} saving={saving} />
    </Panel>
  ))

  return (
    <div class="page">
      <div class="session-head">
        <div class="grow">
          <div class="question">{session.question}</div>
          <div class="meta">
            {session.community.toUpperCase()} · v{session.head_version_number} ·{' '}
            {new Date(session.created_at).toLocaleString()}
          </div>
        </div>
        <button class="quiet" onClick={onBack}>All sessions</button>
        <button class="quiet" onClick={() => downloadRecord(id)}>
          <Download /> Full record
        </button>
      </div>

      {map ? (
        <>
          <div class={`workflow ${workflowOpen ? '' : 'closed'}`} style="margin-top: 22px;">
            <button type="button" class="workflow-head" onClick={() => setWorkflowOpen(!workflowOpen)}>
              <Pip state="done" />
              <span style="font-size: 13px; color: var(--ink); font-weight: 500;">Workflow</span>
              <span class="step-summary">{overview(rows)}</span>
              <Toggle open={workflowOpen} />
            </button>
            {workflowOpen ? <div class="workflow-steps">{stepList}</div> : null}
          </div>
          <EvidenceMap map={map} included={included} />
        </>
      ) : (
        stepList
      )}
    </div>
  )
}

const hintFor = (row) => (row.asks ? 'will ask you' : '')

const overview = (rows) => {
  const done = rows.filter((row) => row.state === 'done').length
  const questions = rows.reduce((n, row) => n + (row.operation?.decisions?.length ?? 0), 0)
  return `${done} steps · you answered ${questions} questions`
}

/** What a step shows when it is open, which depends only on its state. */
export function Body({ row, artifact, onAnswer, onRetry = () => {}, saving }) {
  if (row.state === 'failed') {
    return (
      <>
        <div class="error">{row.operation.error?.message ?? JSON.stringify(row.operation.error)}</div>
        <div class="actions">
          <button class="btn" onClick={() => onRetry(row.operation.id)}>Retry</button>
        </div>
      </>
    )
  }

  if (row.state === 'ask') {
    return (
      <>
        {row.questions.map((decision) => (
          <Question
            key={decision.id}
            decision={decision}
            saving={saving}
            onAnswer={(value) => onAnswer(row.operation.id, decision.key, value)}
          />
        ))}
        {row.questions.length > 1 ? (
          <div class="hint" style="margin-top: 12px;">
            {row.operation.decisions.filter((d) => d.answer != null).length} of{' '}
            {row.operation.decisions.length} saved
          </div>
        ) : null}
        {row.type === 'generate_concept_filters' ? <Trace payload={artifact('concept_filter_loop')} /> : null}
      </>
    )
  }

  if (row.state === 'running') {
    const { progress } = row.operation
    return (
      <>
        {progress?.total ? (
          <div class="bar">
            <div style={`width: ${Math.round((100 * progress.done) / progress.total)}%;`} />
          </div>
        ) : null}
        <div class="counts">
          <div>
            <div class="lab">Done</div>
            <div class="n">{progress?.done ?? 0}</div>
          </div>
          {progress?.failed ? (
            <div class="bad">
              <div class="lab">Failed</div>
              <div class="n">{progress.failed}</div>
            </div>
          ) : null}
        </div>
        <div class="note">{progressText(progress)}</div>
      </>
    )
  }

  const type = ARTIFACT_FOR_STEP[row.type]
  const payload = type ? artifact(type) : null
  if (!payload) return <div class="note">Nothing to show for this step.</div>
  return <Artifact type={type} payload={payload} suggested={artifact(RENDERERS[type]?.suggests)} />
}
