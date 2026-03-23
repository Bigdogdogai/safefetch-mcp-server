#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

SKIP_TEST=0
if [[ "${1:-}" == "--skip-test" ]]; then
  SKIP_TEST=1
fi

PY_BIN=""
if command -v python3.11 >/dev/null 2>&1; then
  PY_BIN="python3.11"
elif command -v python3 >/dev/null 2>&1; then
  PY_BIN="python3"
else
  echo "ERROR: python3.11 or python3 not found."
  exit 1
fi

if ! "${PY_BIN}" - <<'PY'
import sys
ok = (sys.version_info.major == 3 and sys.version_info.minor >= 10)
raise SystemExit(0 if ok else 1)
PY
then
  echo "ERROR: Python >= 3.10 is required (recommended: 3.11)."
  exit 1
fi

if [[ ! -d ".venv" ]]; then
  echo "[1/4] Creating virtual environment..."
  "${PY_BIN}" -m venv .venv
else
  echo "[1/4] Virtual environment already exists, reusing .venv"
fi

echo "[2/4] Installing dependencies..."
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt

if [[ "${SKIP_TEST}" -eq 0 ]]; then
  echo "[3/4] Running self-test..."
  python server.py --self-test
else
  echo "[3/4] Self-test skipped (--skip-test)."
fi

echo "[4/4] Done."
echo
echo "Run MCP server:"
echo "  source .venv/bin/activate && python server.py"
echo
echo "Example mcporter stdio command:"
echo "  mcporter call --stdio \"env WEBFETCH_ALLOW_CIDRS=\${WEBFETCH_ALLOW_CIDRS:-} ${ROOT_DIR}/.venv/bin/python ${ROOT_DIR}/server.py\" fetch_url url=https://example.com caller_id=openclaw-agent max_tokens=3000"
