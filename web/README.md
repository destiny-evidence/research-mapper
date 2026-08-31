# research-mapper web

The Preact UI for the evidence-map workflow. Plan and reasoning:
[`docs/08-web-ui-plan.md`](../docs/08-web-ui-plan.md).

With the rest of the stack:

```sh
docker compose up          # UI on localhost:5173, API on :8080
```

On its own, against an API you are already running:

```sh
npm install
npm run dev      # localhost:5173, proxying /api to localhost:8080
npm test
npm run build    # dist/, ready to upload
```

The dev server proxies `/api`, so development is same-origin and needs no CORS. Deployed, the app
is served from a storage static-website endpoint and calls the API cross-origin; the API allows that
origin through `MAPPER_CORS_ORIGINS` — see §5 of the plan.

`MAPPER_API_TARGET` points the dev proxy somewhere else; `VITE_API_BASE` changes the prefix the app
calls — deployed it is the API's full origin rather than `/api`.

`VITE_KEYCLOAK_URL`, `VITE_KEYCLOAK_REALM` and `VITE_KEYCLOAK_CLIENT_ID` turn on sign-in. All three
or none: unset, `auth.js` sends no bearer token, which is what an API with `MAPPER_AUTH_*` unset
expects. Vite inlines them at build time, so changing one means a rebuild — the deploy workflow
takes them from Terraform-published GitHub environment variables.

`VITE_TERMS=always` pins the disclaimer open and `VITE_TERMS=never` suppresses it, both for
development only — see `.env.example`.

## Where things are

| Path | What it holds |
| --- | --- |
| `src/api.js` | Every HTTP call. Nothing else knows about routes. |
| `src/auth.js` | Keycloak sign-in and the bearer token. Off unless configured. |
| `src/plan.js` | Step order and titles, mirroring `demo/app.js` PLAN. The API has no plan of its own. |
| `src/derive.js` | Pure functions: step states and summaries, artifact diffs, map bucketing. |
| `src/record.js` | Assembles the Full record download from existing routes. |
| `src/ui/artifacts/` | One renderer per artifact type, behind a registry in `index.jsx`. |

Adding an artifact type is a file in `src/ui/artifacts/` and an entry in its `RENDERERS`. An
unregistered type renders as JSON rather than breaking the page.

Adding a workflow step is an entry in `src/plan.js`, and a formatter in `derive.js` if its result
deserves better than the generic one.
