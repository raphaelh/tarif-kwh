#!/usr/bin/env bash
set -euo pipefail
.venv/bin/python -m compileall -q scripts tests
for f in config/*.json; do
  .venv/bin/python -m json.tool "$f" > /dev/null
done
.venv/bin/pytest -q -p no:cacheprovider tests/test_config.py
