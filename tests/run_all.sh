#!/usr/bin/env bash
# Full regression: every suite that needs no billed model call. Usage: tests/run_all.sh [--with-deploy]
# Needs Docker services up (PostgreSQL, Neo4j with the full projection). Stops at the first failure.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
unset all_proxy ALL_PROXY

run() { echo "== $*"; "$@" 2>&1 | { grep -v -E 'StarletteDeprecationWarning|from starlette.testclient import' || true; }; return "${PIPESTATUS[0]}"; }

run python3 tests/test_data_pipeline.py
run python3 tests/test_import_core.py
run $PY tests/test_database_config.py
run $PY tests/test_drill_m7.py
run $PY tests/test_app.py
run $PY tests/test_api.py
run $PY tests/test_project_graph.py
run $PY tests/test_m1_maintenance.py
run $PY tests/test_ai.py
run $PY tests/test_eval_sets.py
if [ -f backend/explain.py ]; then run $PY tests/test_explain.py; else echo "== SKIP tests/test_explain.py (backend/explain.py not written yet)"; fi
(cd frontend && run npm test --silent)
(cd frontend && run npm run build --silent)
if [ "${1:-}" = "--with-deploy" ] || grep -q "StaticFiles" backend/app.py; then run $PY tests/test_deploy.py; fi
echo "ALL PASSED"
