#!/usr/bin/env sh
cd "$(dirname "$0")"
PORT="${1:-8000}"
command -v python3 >/dev/null 2>&1 || { echo "Python 3.9+ needed: https://www.python.org/downloads/"; exit 1; }
python3 -m unittest discover -s tests >/tmp/kestrel_tests.log 2>&1 || { echo "Self-tests failed: /tmp/kestrel_tests.log"; exit 1; }
echo "Open http://127.0.0.1:$PORT"
exec python3 serve.py "$PORT"
