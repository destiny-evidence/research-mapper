# demo UI

A disposable front end for the evidence-mapping workflow. One HTML file, one JS file, no build step.
`serve.py` exists only because the API has no CORS. Delete this directory when the real UI lands.

```bash
uv run python -m research_mapper login      # browser; writes a refresh token into .env
docker compose -f compose.yaml -f demo/compose.yaml up --build
```

Then <http://127.0.0.1:3000>. Against a stack running outside Docker:
`uv run python demo/serve.py --api http://127.0.0.1:8080`.

`demo/` is mounted, so the UI edits live; workflow changes need a rebuild. `?session=<id>` reopens a
session.

## Rough edges

- `PLAN` in `app.js` hardcodes the step order, because `POST /sessions/{id}/operations/` takes a step
  name from the client. Whatever replaces that server-side should let the UI drop it.
- A step stuck in `pending` for 15 seconds gets a warning and a re-run button. That's a stalled or
  absent worker.
- No auth, one local user, every session visible to everyone.
