FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups

COPY research_mapper ./research_mapper
COPY alembic.ini ./
# --reinstall-package: without it a cached wheel is reused and the installed copy of the
# project lags ./research_mapper, so the image silently ships the previous build's code.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --no-editable \
    --reinstall-package research-mapper

EXPOSE 8080
CMD ["python", "-m", "research_mapper", "api"]
