#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f .env ]; then
  cp .env.example .env
  .venv/bin/python -c 'from pathlib import Path; import secrets; p=Path(".env"); p.write_text(p.read_text().replace("replace-with-a-long-random-secret",secrets.token_urlsafe(32))); p.chmod(0o600)'
fi
.venv/bin/python -m app.cli init
exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
