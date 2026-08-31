# research-mapper

A human-in-the-loop agentic workflow for mapping evidence from the DESTINY repository.

![diagram of the intended workflow](assets/Workflow%20Diagram.png)

## How it runs

The API takes requests and queues work. The worker picks work up and runs it, one operation at a time per session. A step that needs an answer from the user records the question and finishes. Answering the question queues the operation again, and it resumes from what it had already written.

## The code

    api/          HTTP surface
    engine/       runs workflows
    workflows/    the workflows themselves
    db/           tables and migrations
    demo/         a throwaway UI
    ui/           the original terminal app

## Running it

Configuration comes from `./.env`. A container cannot see variables you only exported in your shell. Start from `.env.example`.

If the workflow uses the DESTINY repository API, you'll need to log in there first by running the below. This opens a browser and writes a refresh token back into `./.env`, which the API and worker then use. `MAPPER_DESTINY_ENV` has to be set before you run it.

```bash
uv run python -m research_mapper login
```

Then bring up Postgres, apply the migrations, and run the API on `:8080` and the worker:

```bash
docker compose up --build
```

[demo/](demo/) adds an experimental UI on top.

## Configuration

The LLM and the database:

| Variable                                                                   | For                                                            |
| -------------------------------------------------------------------------- | -------------------------------------------------------------- |
| `MAPPER_LLM_MODEL`, `MAPPER_LLM_BASE_URL`, `MAPPER_LLM_API_KEY`            | the LLM                                                        |
| `MAPPER_DB_HOST`, `MAPPER_DB_NAME`, `MAPPER_DB_USER`, `MAPPER_DB_PASSWORD` | Postgres. Deployed, the password is replaced by an Entra token |

There are two separate authentication paths, and they are unrelated to each other.

**Outbound, to DESTINY.** Locally, `login` writes a refresh token and the application exchanges it for access tokens. Deployed, a managed identity is used instead and `login` has no part in it.

| Variable                                           | For                              |
| -------------------------------------------------- | -------------------------------- |
| `MAPPER_DESTINY_ENV`                               | which DESTINY instance to search |
| `MAPPER_DESTINY_REFRESH_TOKEN`                     | written by `login`, local only   |
| `AZURE_CLIENT_ID`, `MAPPER_DESTINY_APPLICATION_ID` | managed identity, deployed only  |

**Inbound, to our own API.** Callers present a bearer token, which is checked against Keycloak.

| Variable                                      | For                                       |
| --------------------------------------------- | ----------------------------------------- |
| `MAPPER_AUTH_ISSUER`, `MAPPER_AUTH_CLIENT_ID` | the issuer and client to validate against |
| `MAPPER_CORS_ORIGINS`                         | origins allowed to call the API from a browser |

This one is off unless both are set. With it off, the API accepts every request and attributes it all to a single local user.

`MAPPER_CORS_ORIGINS` is a comma-separated list and is likewise off when unset. It is needed because the deployed UI is served from a storage static-website endpoint and so calls the API cross-origin; locally the dev server proxies `/api` and nothing is cross-origin.

## The terminal app

The original interactive CLI. Install it standalone so `research-mapper` is available anywhere on your machine:

```bash
uv tool install git+https://github.com/destiny-evidence/research-mapper
research-mapper
```

Run from outside a clone, it reads `~/.config/research-mapper/.env` (`%APPDATA%\research-mapper\.env` on Windows). `--env-file` overrides it, and exported shell variables beat both.

## Development

Python 3.14 and [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo-url>
cd research-mapper
uv sync
uv run pytest
```

Tests need Postgres on 5433 and create their own database on it. `docker compose up -d db` is enough.

After changing a model, generate a migration against a database that is already at head:

```bash
uv run alembic revision --autogenerate -m "what changed"
```

Read what it wrote before committing it. Apply migrations with `uv run python -m research_mapper migrate`, or by bringing the stack up.

## License

[Apache License 2.0](LICENSE)
