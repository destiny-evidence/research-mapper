#!/bin/sh
uv run pytest -m "not integration" --tb=short
exit 0