#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r requirements.txt
python manage.py collectstatic --noinput
# the visitors' countries (observations/geo.py): never fails the build
python scripts/fetch_geoip.py || true
