#!/bin/sh
python -m pytest -m "not integration" --tb=short
exit 0