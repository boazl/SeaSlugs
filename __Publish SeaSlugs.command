#!/bin/bash
cd "$(dirname "$0")" || exit 1
./.venv/bin/python scripts/publish.py
result=$?
printf '\nPress Enter to close…'
read -r
exit "$result"
