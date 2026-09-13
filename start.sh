#!/usr/bin/env bash
set -euo pipefail
python - <<'PYTHON'
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
root = Path(os.environ.get("SEASLUGS_DATA_DIR", "/var/data"))
if not root.is_dir() or not os.access(root, os.W_OK):
    raise SystemExit("Persistent data directory is missing or not writable: " + str(root))
(root / "media").mkdir(exist_ok=True)
database = root / "db.sqlite3"
if database.exists():
    backups = root / "backups"
    backups.mkdir(exist_ok=True)
    target = backups / ("before-deploy-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f") + ".sqlite3")
    with sqlite3.connect(str(database)) as source, sqlite3.connect(str(target)) as destination:
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("Database backup verification failed; deployment stopped.")
    target.chmod(0o600)
    print("Verified database backup before migrations:", target, flush=True)
PYTHON
python manage.py migrate --noinput
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 2 --access-logfile - --error-logfile -
