const day = (iso) =>
  new Date(iso).toLocaleDateString(undefined, {
    day: "numeric",
    month: "short",
  });

export function Sessions({ sessions, waiting = new Set(), onOpen, onNew }) {
  return (
    <>
      <div class="list-head">
        <span class="list-title">Sessions</span>
        <span class="grow" />
        <button class="btn" onClick={onNew}>
          Ask a new question
        </button>
      </div>
      {sessions.length === 0 ? <div class="note">Nothing here yet.</div> : null}
      {sessions.map((session) => (
        <button
          type="button"
          class="session-row"
          key={session.id}
          onClick={() => onOpen(session.id)}
        >
          <span class="session-q">{session.question}</span>
          {waiting.has(session.id) ? (
            <span style="font-size: 12px; color: var(--amber);">needs you</span>
          ) : null}
          <span class="pill">{session.community.toUpperCase()}</span>
          <span class="when">{day(session.created_at)}</span>
        </button>
      ))}
    </>
  );
}
