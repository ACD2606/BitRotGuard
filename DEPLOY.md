# Deploying to Render

This folder is the whole project — desktop app included. Only a subset of
it is relevant to deploying the *web* version; here's what that involves.

## What changed for the web deploy
- `bitrot_guard.py` (tkinter desktop app) is **not imported by the server**.
  It can't run headless — no display, and Render's Python env doesn't ship
  Tk libs — so it just sits in the repo for local desktop use and isn't
  touched by the deploy.
- Its non-GUI logic (Hamming encode/decode, `.hprot` protect/heal, bit-flip
  simulator, file-kind detection) lives in `core_engine.py`, which has zero
  GUI dependencies. `app.py` and `ecc_engines.py` import from there.
- Two requirements files:
  - `requirements.txt` — full set, for running either app locally
    (`bitrot_guard.py` or `app.py`). Includes `numpy`/`matplotlib` for the
    desktop app's optional live chart.
  - `requirements-webapp.txt` — what `app.py` actually needs. Used by both
    `Setup and Run.bat` (local one-click launch) and Render. Drops
    `numpy`/`matplotlib` (desktop-only, dead weight here) and adds
    `gunicorn` (only exercised in production, harmless locally).
    `render.yaml` points here.
- `app.py`'s `app.run(...)` reads `PORT` from the environment and binds
  `0.0.0.0` (required by Render; gunicorn runs it in production regardless,
  this just keeps `python app.py` working locally too).

## Steps
1. Push this whole folder to a GitHub repo.
2. On [render.com](https://render.com) → **New > Blueprint** → connect the
   repo. It'll read `render.yaml` and configure everything automatically.
   (No Blueprint? New > Web Service → same repo → Build:
   `pip install -r requirements-webapp.txt`, Start:
   `gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120`.)
3. Deploy. First build takes ~2-3 min (Pillow/fpdf2 wheels).
4. Open the `.onrender.com` URL Render gives you — that's the live app.

## Notes
- Free tier spins down after 15 min idle and cold-starts on the next
  request (~30-50s). Fine for a demo link, mention it if someone's timing
  the first load.
- Session state (`session = {...}` in `app.py`) is a single in-memory dict —
  same as the original design, works for one demo user at a time, resets on
  redeploy/restart. Not something this refactor changed.
