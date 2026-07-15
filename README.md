# BitRot Guard v3

A modern web-based demo of protecting files against silent "bit rot" using
Hamming(7,4) error-correcting codes — with interactive visualizations and
ECC comparison mode.

## Features

### 🛡️ Core: Protect → Corrupt → Heal
Choose a file → encode with Hamming(7,4) ECC → simulate random bit flips →
heal the protected copy and watch it recover perfectly, while the unprotected
copy stays broken.

### 🔬 ECC Comparison Mode
Compare **No Protection** vs **Simple Parity** vs **Hamming(7,4)** side by side
to see the tradeoff between overhead and protection.

### 📊 Interactive Dashboard
- **Integrity Over Time** chart (animated, real-time)
- **Corruption Heatmap** — visual map of where bit flips landed
- **File Health Gauges** — SVG animated integrity percentage
- **Stat Cards** — file size, overhead, errors corrected, SHA-256 status

### 🎮 Interactive Bit Visualization
- Canvas-based bit grid showing individual bits
- **Click to flip** — manually corrupt individual bits
- **Adjustable corruption slider** — choose 1–50 bit flips
- Diff highlighting shows exactly which bits changed

### 📄 PDF Report Export
Generate a downloadable PDF report of your full demo session.

### ✨ Premium UI
- Dark glassmorphism theme with purple/cyan/green accents
- Smooth animations and micro-interactions
- Drag-and-drop file upload
- Particle celebration on perfect recovery
- Responsive design

## Quick Start

### Option 1: Double-click
1. Install Python 3.9+ from https://python.org (check "Add to PATH")
2. Double-click the launcher for your OS — installs deps + opens browser:
   - Windows: **`Setup and Run.bat`**
   - macOS: **`Setup and Run.command`** (right-click → Open the first time,
     since it's unsigned)
   - Linux: run `./setup_and_run.sh` from a terminal (or `python3 setup_and_run.py`)

### Option 2: Manual
```bash
pip install -r requirements-webapp.txt
python app.py
```
Then open http://localhost:5000

## What's in This Folder

| File | Purpose |
|------|---------|
| `app.py` | Flask web server (API backend) |
| `core_engine.py` | Hamming(7,4) + `.hprot` core logic, no GUI deps — imported by `app.py` and `ecc_engines.py` |
| `bitrot_guard.py` | Original tkinter desktop app (standalone; not imported by the web server) |
| `hamming_ecc_demo.py` | Standalone ~200-line CLI demo of the core ECC logic — zero dependencies, no Flask/tkinter |
| `ecc_engines.py` | ECC comparison engines (parity, Hamming) |
| `static/` | Web frontend (HTML, CSS, JavaScript) |
| `requirements.txt` | Full Python dependencies (local use — either app) |
| `requirements-webapp.txt` | Trimmed dependencies for `app.py` — used by all three launchers below and Render |
| `render.yaml` / `DEPLOY.md` | Render deployment config + steps |
| `Setup and Run.bat` | One-click launcher (Windows) |
| `Setup and Run.command` | One-click launcher (macOS) |
| `setup_and_run.sh` | Launcher for Linux / manual macOS terminal use |
| `setup_and_run.py` | Shared cross-platform install+launch logic all three call into |
| `sample_*.txt/jpg/png` | Sample files to demo with |

## Run the Original Tkinter App

The original desktop version still works:
```bash
python bitrot_guard.py
```

## Self-Test
```bash
python bitrot_guard.py --selftest
```

## Standalone Core Demo

Just the Hamming(7,4) math, protect/corrupt/heal, no Flask/tkinter/deps:
```bash
python hamming_ecc_demo.py [file]      # omit file to use a built-in sample
python hamming_ecc_demo.py --selftest
```

## Deploy the Web App

See `DEPLOY.md` for pushing `app.py` to Render (`render.yaml` included for
one-click Blueprint deploy).
