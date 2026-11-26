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
stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-%f")
# The main database and the separate support (financial) database, each backed up and verified before migrations.
for database, prefix in ((root / "db.sqlite3", "before-deploy-"), (root / "support.sqlite3", "support-before-deploy-")):
    if not database.exists():
        continue
    backups = root / "backups"
    backups.mkdir(exist_ok=True)
    target = backups / (prefix + stamp + ".sqlite3")
    with sqlite3.connect(str(database)) as source, sqlite3.connect(str(target)) as destination:
        source.backup(destination)
        if destination.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit("Database backup verification failed; deployment stopped.")
    target.chmod(0o600)
    print("Verified database backup before migrations:", target, flush=True)
PYTHON
python manage.py migrate --noinput
python manage.py migrate --database support --noinput
exec gunicorn config.wsgi:application --bind "0.0.0.0:${PORT:-8000}" --workers 1 --threads 2 --timeout 300 --access-logfile - --error-logfile -
