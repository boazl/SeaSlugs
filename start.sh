#!/usr/bin/env bash
set -euo pipefail
python - <<'PYTHON'
import os
from pathlib import Path
root = Path(os.environ.get("SEASLUGS_DATA_DIR", "/var/data"))
if not root.is_dir() or not os.access(root, os.W_OK):
    raise SystemExit("Persistent data directory is missing or not writable: " + str(root))
(root / "media").mkdir(exist_ok=True)
PYTHON
python manage.py migrate --noinput
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 2 --access-logfile - --error-logfile -
