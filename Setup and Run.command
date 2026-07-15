#!/bin/bash
# BitRot Guard v3 - Setup & Run (macOS / Linux)
cd "$(dirname "$0")"

if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 not found."
    echo "Install it from https://python.org (or 'brew install python3' on macOS) and try again."
    read -p "Press Enter to exit..."
    exit 1
fi

python3 setup_and_run.py
echo
read -p "Press Enter to exit..."
