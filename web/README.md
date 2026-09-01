# research-mapper web

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
