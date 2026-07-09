# research-mapper

A human-in-the-loop agentic workflow for mapping evidence from the DESTINY repository. 

## Architecture

![iagram of the intented workflow](assets/Workflow%20Diagram.png)

## Getting Started

### Prerequisites

- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Access to a DESTINY repository instance

### Installation

```bash
git clone <repo-url>
cd research-mapper
uv sync
```

### Configuration

Copy the `.env.example` file below into a `.env` file at the project root and fill in your credentials:

```bash
# MAPPER_DESTINY_ENV and MAPPER_DESTINY_BASE_URL default to the production
# DESTINY instance — only set these if you're developing against a
# staging/development instance.

MAPPER_LLM_MODEL=azure/gpt-4o
MAPPER_LLM_BASE_URL=https://your-azure-openai-instance.openai.azure.com/
MAPPER_LLM_API_KEY=...
```

### Running

```bash
uv run main.py
```

You'll be prompted to authenticate, then asked for your research question. The agent will generate a set of database search queries and allow you to validate them before running the evidence search.

## TODO


## DONE
- [X] **Unit tests** — test core components (query generator, tools, validation logic) with mocked SDK responses, suitable for CI/CD
- [X] **Live functional tests** — integration tests against a real DESTINY instance and LLM providers for local pre-release verification
- [X] **Async evidence gathering** — run ReAcT agents concurrently across search queries ~~using DSPy's native async support and async tool implementations~~
- [X] **More Transparent Logging** — present arg choices of the evidence retrieval agents (i.e. start & end year, sort, and page) alongside LLM reasoning for which Evidence to return.
