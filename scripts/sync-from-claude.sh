#!/bin/sh
# Публикует сохранённые облачные навыки, проверяя версию-основание пакета.
set -eu
cd "$(dirname "$0")/.."
exec python3 scripts/sync-skills.py publish-cloud
