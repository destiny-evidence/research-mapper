# demo UI

A disposable front end. One HTML file, one JS file, no build step. `serve.py` exists only because the
API has no CORS. Delete this directory when the real UI lands.

```bash
uv run python -m research_mapper login      # browser; writes a refresh token into .env
docker compose -f compose.yaml -f demo/compose.yaml up --build
```

Then <http://127.0.0.1:3000>. Against a stack running outside Docker:
`uv run python demo/serve.py --api http://127.0.0.1:8080`.

`demo/` is mounted, so the UI edits live; workflow changes need a rebuild. `?session=<id>` reopens a
session.
