# research-mapper web

The Preact UI for the evidence-map workflow. Plan and reasoning:
[`docs/08-web-ui-plan.md`](../docs/08-web-ui-plan.md).

```sh
npm install
npm run dev      # localhost:5173, proxying /api to localhost:8080
npm test
npm run build    # dist/, ready to upload
```

The dev server proxies `/api` because the API has no CORS. In production the two must sit behind
one hostname, or the API needs `CORSMiddleware` — see §5 of the plan.

`VITE_API_BASE` overrides the API prefix if you need it to point somewhere else.

## Where things are

| Path | What it holds |
| --- | --- |
| `src/api.js` | Every HTTP call. Nothing else knows about routes. |
| `src/plan.js` | Step order and titles, mirroring `demo/app.js` PLAN. The API has no plan of its own. |
| `src/derive.js` | Pure functions: step states and summaries, artifact diffs, map bucketing. |
| `src/record.js` | Assembles the Full record download from existing routes. |
| `src/ui/artifacts/` | One renderer per artifact type, behind a registry in `index.jsx`. |

Adding an artifact type is a file in `src/ui/artifacts/` and an entry in its `RENDERERS`. An
unregistered type renders as JSON rather than breaking the page.

Adding a workflow step is an entry in `src/plan.js`, and a formatter in `derive.js` if its result
deserves better than the generic one.
