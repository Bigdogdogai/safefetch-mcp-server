#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "${ROOT_DIR}"

if [[ ! -f ".venv/bin/activate" ]]; then
  echo "ERROR: .venv not found. Please run: bash bootstrap.sh"
  exit 1
fi

source .venv/bin/activate
exec python server.py
