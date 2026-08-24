# research-mapper

A human-in-the-loop agentic workflow for mapping evidence from the DESTINY repository. 

## Architecture

![diagram of the intended workflow](assets/Workflow%20Diagram.png)

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- A DESTINY account to authenticate with (defaults to the public production instance)

### Installation

Install it as a standalone tool, so `research-mapper` is available anywhere on your machine:

```bash
uv tool install git+https://github.com/destiny-evidence/research-mapper
```

To upgrade later: `uv tool upgrade research-mapper`.

### Configuration

`research-mapper` needs the following variables (see `.env.example`):

```bash
MAPPER_LLM_MODEL=azure/gpt-4o
MAPPER_LLM_BASE_URL=https://your-azure-openai-instance.openai.azure.com/
MAPPER_LLM_API_KEY=...
```

There are several ways to provide them, checked in this order (first match per variable wins):

1. **Exported shell variables** — add them to your `~/.bashrc`/`~/.zshrc`/etc. The `MAPPER_` prefix makes these safe to export globally without colliding with other tools.
2. **`--env-file <path>`** — pass an explicit `.env` file on the command line.
3. **`./.env`** — a `.env` file in the current directory (or a parent directory), handy for a local clone.
4. **A machine-wide fallback file** — `~/.config/research-mapper/.env` (or `%APPDATA%\research-mapper\.env` on Windows), useful when running `research-mapper` from arbitrary directories.

### Running

```bash
research-mapper
```

You'll be prompted to authenticate, then asked for your research question. The agent will generate a set of database search queries and allow you to validate them before running the evidence search.

## Development

To run `research-mapper` from source:

```bash
git clone <repo-url>
cd research-mapper
uv sync
uv run research-mapper
```

### The API and worker

`compose.yaml` brings up Postgres, applies the migrations, and runs both the API (`:8080`) and the
operation worker:

```bash
docker compose up --build
```

Credentials come from `./.env` — a container cannot see variables you only exported in your shell.
`MAPPER_API_PORT` moves the published API port. For the API alone, without an LLM or DESTINY, see
[demo/](demo/).

## License

[Apache License 2.0](LICENSE)
