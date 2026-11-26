#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-.venv/bin/python}"
if [ ! -x "$PY" ]; then
  PY=python3
fi

LLM_PROVIDER=mock PYTHONDONTWRITEBYTECODE=1 "$PY" -m pytest -o addopts= -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 "$PY" eval/check_results.py --strict
