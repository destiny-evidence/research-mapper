FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.10 /uv /uvx /bin/

# ttyd serves the terminal UI over HTTP. Debian doesn't package it, so this is
# the upstream static build. See TEMPORARY note in entrypoint.sh.
ADD --chmod=755 https://github.com/tsl0922/ttyd/releases/download/1.7.7/ttyd.x86_64 /usr/local/bin/ttyd

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-default-groups

COPY research_mapper ./research_mapper
COPY entrypoint.sh ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-default-groups --no-editable

EXPOSE 8080
CMD ["ttyd", "--writable", "--port", "8080", "--terminal-type", "xterm-256color", \
     "-t", "titleFixed=research-mapper", "/app/entrypoint.sh"]
