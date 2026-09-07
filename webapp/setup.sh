#!/usr/bin/env bash
# APIx setup — macOS and Linux.
#   bash webapp/setup.sh
set -euo pipefail
cd "$(dirname "$0")/.."

echo "APIx setup"
echo "----------------------------------------------------------------"

PY=""
for c in python3.12 python3.11 python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    v=$("$c" -c 'import sys;print("%d.%d"%sys.version_info[:2])' 2>/dev/null || echo 0)
    maj=${v%%.*}; min=${v##*.}
    if [ "$maj" = "3" ] && [ "$min" -ge 10 ]; then PY="$c"; break; fi
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is required. Install it from python.org and re-run."
  exit 1
fi
echo "  python      $($PY --version)"

if [ ! -d .venv ]; then
  echo "  venv        creating .venv"
  "$PY" -m venv .venv
else
  echo "  venv        .venv already exists"
fi
# shellcheck disable=SC1091
source .venv/bin/activate

echo "  packages    installing (a minute or two)"
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

echo "  chromium    installing the browser Playwright drives"
python -m playwright install chromium >/dev/null

echo "  database    applying schemas"
python - <<'PYEOF'
from webapp.run import ensure_database
print("              ", ensure_database())
PYEOF

echo "----------------------------------------------------------------"
echo "Done. Two commands from here:"
echo
echo "  source .venv/bin/activate"
echo "  python -m apix.cli useradd --generate-password   # once, for the console"
echo "  python -m webapp.run                             # start it"
echo
echo "Then open http://localhost:8000"
