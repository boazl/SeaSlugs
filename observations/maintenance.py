"""Site-wide maintenance lock, used only while a full database replacement
(see db_replace.py) is in progress. A flag file -- not a database row, since
the database itself is what's being replaced -- marks the site as locked;
MaintenanceModeMiddleware blocks ordinary traffic while it exists."""
from pathlib import Path
from django.conf import settings


def flag_path():
    return Path(settings.DATA_DIR) / 'maintenance.flag'


def is_locked():
    return flag_path().exists()


def lock():
    path = flag_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('locked')
    path.chmod(0o600)


def unlock():
    flag_path().unlink(missing_ok=True)
