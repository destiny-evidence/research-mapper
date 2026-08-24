# demo UI

A disposable front end for demoing the evidence-mapping workflow. One HTML file, one JS file, no
build step. It talks to the normal API; `serve.py` only exists because the API has no CORS.

Delete this whole directory when the real UI lands.

## Run it

Everything — database, API, worker and UI — with the LLM and DESTINY replaced by canned data:

```bash
docker compose -f demo/compose.yaml up --build
```

Then open <http://127.0.0.1:3000>. Nothing leaves the machine and nothing costs money.

The image holds a snapshot of `research_mapper`, so rebuild after changing workflow code. `demo/`
itself is mounted, so the UI and the stubs are editable with a container restart and no rebuild.

`DEMO_DELAY` (default `0.3`) is the fake per-item latency — raise it to make progress bars visible
while presenting, drop it to `0` to blast through. `DEMO_UI_PORT`, `DEMO_API_PORT` and
`DEMO_DB_PORT` move the published ports if something already holds them.

`docker compose -f demo/compose.yaml down -v` throws the sessions away.

### Against the real thing

Point the UI at a live stack instead — the root `compose.yaml`, or the API and worker running on
your machine:

```bash
uv run python demo/serve.py --api http://127.0.0.1:8080
```

That path needs the usual `MAPPER_*` credentials, and DESTINY authentication that works
non-interactively.

### Without Docker

```bash
uv run python demo/offline.py api      # or: python -m research_mapper api
uv run python demo/offline.py worker
uv run python demo/serve.py
```

`commands.api()` hardcodes port 8080, and Docker Desktop may already be listening there. If it is,
`offline.py api --port 8090` moves it and `serve.py --api http://127.0.0.1:8090` follows.

## What it shows

The pipeline rail on the left is the nine registered steps. The UI runs them in order, polls the
operation it started, and stops whenever the operation parks on a decision. Answer it and the same
operation resumes — no replay. Artifacts appear in the sidebar as they are written; click one to
read its stored payload, including the ReAct trajectory the concept-filter loop pauses on.

`?session=<id>` reopens a session, so a reload — or a laptop swap mid-demo — lands back where you
were.

## Known rough edges

- **The step order lives here, not in the backend.** `PLAN` in `app.js` hardcodes the sequence,
  because `POST /sessions/{id}/operations/` takes a step name from the client. Whatever replaces
  that on the server should let the UI drop it.
- If a step sits in `pending` for 15 seconds the UI says so and offers to re-run it. That is a
  stalled or absent worker, not something the UI can fix.
- No auth, one local user, and every session is visible to everyone.
