#!/bin/bash
# Starts the Inkscape MCP server on macOS, creating its virtual environment on first run.
# stdout belongs to the MCP protocol, so setup output goes to stderr.
# The extension itself runs inside Inkscape's bundled Python, which ships inkex and lxml.

set -e
cd "$(dirname "$0")"

if [ ! -x venv/bin/python ]; then
    PYTHON=""
    for candidate in python3.13 python3.12 python3.11 python3.10 \
        /opt/homebrew/bin/python3.13 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3.11 \
        /usr/local/bin/python3.13 /usr/local/bin/python3.12 /usr/local/bin/python3.11; do
        if command -v "$candidate" >/dev/null 2>&1; then PYTHON="$candidate"; break; fi
    done
    if [ -z "$PYTHON" ]; then
        echo "inkmcp needs Python 3.10 or newer (brew install python)." >&2
        exit 1
    fi
    echo "Creating inkmcp's Python environment with $PYTHON..." >&2
    "$PYTHON" -m venv venv
    venv/bin/pip install --quiet -r requirements.txt >&2
fi

exec venv/bin/python main.py
