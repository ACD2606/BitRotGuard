#!/usr/bin/env python3
"""
Setup and Run — cross-platform launcher for BitRot Guard's web app.
Installs dependencies, opens your browser, then starts app.py.

Called by:
  Windows  -> Setup and Run.bat
  macOS    -> Setup and Run.command
  Linux    -> setup_and_run.sh  (or just: python3 setup_and_run.py)

Needs Python 3.9+ already installed — this script doesn't install Python
itself, only the app's pip dependencies.
"""

import os
import subprocess
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
REQS = os.path.join(HERE, "requirements-webapp.txt")
APP = os.path.join(HERE, "app.py")
PORT = int(os.environ.get("PORT", 5000))


def install_deps():
    print("=" * 60)
    print("  BitRot Guard v3 - installing dependencies")
    print("=" * 60)
    result = subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", REQS])
    if result.returncode != 0:
        print("[WARNING] Some dependencies failed to install via pip.")
        print("Trying to launch app anyway...")
    print()


def open_browser_when_ready():
    time.sleep(2)
    try:
        webbrowser.open(f"http://localhost:{PORT}")
    except Exception:
        pass  # headless machine, or no default browser - not fatal


def main():
    if sys.version_info < (3, 9):
        print(f"[ERROR] Python 3.9+ required — you're running {sys.version.split()[0]}.")
        print("Install a newer Python from https://python.org and try again.")
        input("Press Enter to exit...")
        sys.exit(1)

    install_deps()

    print("=" * 60)
    print("  Dependencies ready. Launching BitRot Guard...")
    print(f"  Open http://localhost:{PORT} in your browser")
    print("=" * 60)
    print()

    threading.Thread(target=open_browser_when_ready, daemon=True).start()

    # Run app.py as its own process, matching `python app.py` exactly
    result = subprocess.run([sys.executable, APP])
    if result.returncode != 0:
        print()
        print("[CRASH] The server crashed or shut down unexpectedly.")
        print("Read the error message above to see what went wrong.")
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()
