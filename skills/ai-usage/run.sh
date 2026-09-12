#!/bin/sh
# POSIX shim. The real entry point is run.py, which also works on Windows.
dir=$(dirname "$0")
if command -v python3 >/dev/null 2>&1; then
  exec python3 "$dir/run.py" "$@"
fi
exec python "$dir/run.py" "$@"
