"""
BitRot Guard — Flask Web Server
================================
REST API backend that wraps the existing Hamming(7,4) engine and ECC
comparison module into a modern web application.

Run:  python app.py
Then: open http://localhost:5000 in your browser
"""

import os
import sys
import hashlib
import random
import base64
import shutil
import time
from pathlib import Path

from flask import (
    Flask, request, jsonify, send_file, send_from_directory, Response,
)

# ---------------------------------------------------------------------------
# Import project modules (tkinter-free core — safe to import on a headless
# server; the original bitrot_guard.py desktop app is not part of this deploy)
# ---------------------------------------------------------------------------
from core_engine import (
    hamming_encode_bytes, hamming_decode_bytes,
    protect_file, heal_file, read_protected_header,
    flip_random_bits, detect_kind,
)
from ecc_engines import compare_all

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024  # 16 MB upload limit

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "uploads")
ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# In-memory session state (single-user demo)
# ---------------------------------------------------------------------------
session = {
    "original_path": None,
    "original_name": None,
    "original_size": 0,
    "protected_path": None,
    "unprotected_path": None,
    "healed_path": None,
    "file_kind": None,
    "unprot_flip_history": [],
    "prot_flip_history": [],
    "total_flips_applied": 0,
    "errors_corrected": 0,
    "hash_ok": None,
    "encoded_size": 0,
    "state": {
        "chosen": False,
        "protected": False,
        "corrupted": False,
        "healed": False,
        "healed_ok": None,
    },
    "integrity_timeline": [],
    "original_hash": None,
    "corruption_rounds": 0,
}


def _reset_session(keep_file=False):
    """Reset session to initial state."""
    global session
    if not keep_file:
        session["original_path"] = None
        session["original_name"] = None
        session["original_size"] = 0
        session["file_kind"] = None
        session["original_hash"] = None
        session["state"]["chosen"] = False

    session["protected_path"] = None
    session["unprotected_path"] = None
    session["healed_path"] = None
    session["unprot_flip_history"] = []
    session["prot_flip_history"] = []
    session["total_flips_applied"] = 0
    session["errors_corrected"] = 0
    session["hash_ok"] = None
    session["encoded_size"] = 0
    session["state"]["protected"] = False
    session["state"]["corrupted"] = False
    session["state"]["healed"] = False
    session["state"]["healed_ok"] = None
    session["integrity_timeline"] = []
    session["corruption_rounds"] = 0


# ---------------------------------------------------------------------------
# Serve frontend
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return send_from_directory("static", "index.html")


# ---------------------------------------------------------------------------
# API: File Upload
# ---------------------------------------------------------------------------

@app.route("/api/upload", methods=["POST"])
def upload_file():
    _reset_session()

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    f = request.files["file"]
    if not f.filename:
        return jsonify({"error": "Empty filename"}), 400

    # Save uploaded file
    safe_name = f.filename.replace(os.sep, "_")
    save_path = os.path.join(UPLOAD_DIR, safe_name)
    f.save(save_path)

    file_size = os.path.getsize(save_path)
    file_kind = detect_kind(save_path)

    with open(save_path, "rb") as fp:
        file_hash = hashlib.sha256(fp.read()).hexdigest()

    session["original_path"] = save_path
    session["original_name"] = safe_name
    
    base = os.path.splitext(safe_name)
    name, ext = base[0], base[1]
    unprotected_path = os.path.join(ARTIFACTS_DIR, f"{name}_unprotected{ext}")
    shutil.copy2(save_path, unprotected_path)
    session["unprotected_path"] = unprotected_path

    session["original_size"] = file_size
    session["file_kind"] = file_kind
    session["original_hash"] = file_hash
    session["state"]["chosen"] = True
    session["integrity_timeline"] = [
        {"step": "Start", "protected": 100, "unprotected": 100}
    ]

    return jsonify({
        "success": True,
        "filename": safe_name,
        "size": file_size,
        "kind": file_kind,
        "hash": file_hash,
    })


# ---------------------------------------------------------------------------
# API: Protect
# ---------------------------------------------------------------------------

@app.route("/api/protect", methods=["POST"])
def do_protect():
    if not session["original_path"]:
        return jsonify({"error": "No file selected"}), 400

    base = os.path.splitext(session["original_name"])
    name, ext = base[0], base[1]

    protected_path = os.path.join(ARTIFACTS_DIR, f"{name}_protected.hprot")
    unprotected_path = session["unprotected_path"]

    _, orig_size, enc_size = protect_file(session["unprotected_path"], protected_path)

    session["protected_path"] = protected_path
    session["unprotected_path"] = unprotected_path
    session["encoded_size"] = enc_size
    session["state"]["protected"] = True
    session["unprot_flip_history"] = []
    session["prot_flip_history"] = []
    session["total_flips_applied"] = 0
    session["corruption_rounds"] = 0

    overhead = (enc_size / orig_size - 1) * 100 if orig_size else 0

    session["integrity_timeline"].append(
        {"step": "Protected", "protected": 100, "unprotected": 100}
    )

    return jsonify({
        "success": True,
        "original_size": orig_size,
        "encoded_size": enc_size,
        "overhead_pct": round(overhead, 1),
        "protected_file": os.path.basename(protected_path),
        "unprotected_file": os.path.basename(unprotected_path),
    })


# ---------------------------------------------------------------------------
# API: Corrupt
# ---------------------------------------------------------------------------

@app.route("/api/corrupt", methods=["POST"])
def do_corrupt():
    if not session["unprotected_path"]:
        return jsonify({"error": "No file to corrupt"}), 400

    data = request.get_json(silent=True) or {}
    num_flips = data.get("num_flips", random.randint(3, 7))
    num_flips = max(1, min(num_flips, 50))

    # Flip bits in protected file (if it exists)
    prot_flips = []
    if session.get("protected_path"):
        info = read_protected_header(session["protected_path"])
        prot_flips = flip_random_bits(
            session["protected_path"], num_flips,
            region_start=info["header_len"]
        )
    # Flip bits in unprotected file
    unprot_flips = flip_random_bits(session["unprotected_path"], num_flips)

    session["prot_flip_history"].extend(prot_flips)
    session["unprot_flip_history"].extend(unprot_flips)
    session["total_flips_applied"] += num_flips
    session["state"]["corrupted"] = True
    session["corruption_rounds"] += 1

    # Compute integrity percentages
    with open(session["original_path"], "rb") as f:
        orig_bytes = f.read()
    with open(session["unprotected_path"], "rb") as f:
        unprot_bytes = f.read()

    n = min(len(orig_bytes), len(unprot_bytes))
    diff_count = sum(1 for i in range(n) if orig_bytes[i] != unprot_bytes[i])
    unprot_pct = round(100.0 * (1 - diff_count / n), 4) if n else 0

    session["integrity_timeline"].append({
        "step": f"Corrupt #{session['corruption_rounds']}",
        "protected": 100,  # still encoded, integrity unknown until heal
        "unprotected": unprot_pct,
    })

    # Format flip details for display
    flip_details = []
    for flip in unprot_flips:
        flip_details.append({
            "byte_index": flip["byte_index"],
            "bit_index": flip["bit_index"],
            "old_byte": format(flip["old_byte"], "08b"),
            "new_byte": format(flip["new_byte"], "08b"),
        })

    return jsonify({
        "success": True,
        "num_flips": num_flips,
        "total_flips": session["total_flips_applied"],
        "corruption_round": session["corruption_rounds"],
        "unprotected_integrity": unprot_pct,
        "flip_details": flip_details,
    })


# ---------------------------------------------------------------------------
# API: Heal
# ---------------------------------------------------------------------------

@app.route("/api/heal", methods=["POST"])
def do_heal():
    if not session["state"]["corrupted"]:
        return jsonify({"error": "No corruption to heal"}), 400

    base = os.path.splitext(session["original_name"])
    name, ext = base[0], base[1]
    healed_path = os.path.join(ARTIFACTS_DIR, f"{name}_healed{ext}")

    _, errors_corrected, ok = heal_file(session["protected_path"], healed_path)

    session["healed_path"] = healed_path
    session["errors_corrected"] = errors_corrected
    session["hash_ok"] = ok
    session["state"]["healed"] = True
    session["state"]["healed_ok"] = ok

    # Compute healed integrity
    with open(session["original_path"], "rb") as f:
        orig_bytes = f.read()
    with open(healed_path, "rb") as f:
        healed_bytes = f.read()
    with open(session["unprotected_path"], "rb") as f:
        unprot_bytes = f.read()

    n_h = min(len(orig_bytes), len(healed_bytes))
    h_diff = sum(1 for i in range(n_h) if orig_bytes[i] != healed_bytes[i])
    healed_pct = round(100.0 * (1 - h_diff / n_h), 4) if n_h else 0

    n_u = min(len(orig_bytes), len(unprot_bytes))
    u_diff = sum(1 for i in range(n_u) if orig_bytes[i] != unprot_bytes[i])
    unprot_pct = round(100.0 * (1 - u_diff / n_u), 4) if n_u else 0

    session["integrity_timeline"].append({
        "step": "Healed",
        "protected": healed_pct,
        "unprotected": unprot_pct,
    })

    # Build flip log
    unprot_log = []
    for flip in session["unprot_flip_history"][:20]:
        unprot_log.append({
            "byte_index": flip["byte_index"],
            "old_byte": format(flip["old_byte"], "08b"),
            "new_byte": format(flip["new_byte"], "08b"),
        })

    prot_log = []
    for flip in session["prot_flip_history"][:20]:
        prot_log.append({
            "byte_index": flip["byte_index"],
            "old_byte": format(flip["old_byte"], "08b"),
            "new_byte": format(flip["new_byte"], "08b"),
        })

    return jsonify({
        "success": True,
        "errors_corrected": errors_corrected,
        "hash_ok": ok,
        "healed_integrity": healed_pct,
        "unprotected_integrity": unprot_pct,
        "total_flips": session["total_flips_applied"],
        "unprot_flip_log": unprot_log,
        "prot_flip_log": prot_log,
    })


# ---------------------------------------------------------------------------
# API: Manual Bit Flip
# ---------------------------------------------------------------------------

@app.route("/api/manual-flip", methods=["POST"])
def manual_flip():
    if not session["unprotected_path"]:
        return jsonify({"error": "No unprotected file to flip"}), 400

    data = request.get_json(silent=True) or {}
    byte_index = data.get("byte_index", 0)
    bit_index = data.get("bit_index", 0)

    # Flip in unprotected
    with open(session["unprotected_path"], "rb") as f:
        buf = bytearray(f.read())

    if byte_index >= len(buf):
        return jsonify({"error": "Byte index out of range"}), 400

    old_byte = buf[byte_index]
    buf[byte_index] ^= (1 << (7 - bit_index))
    new_byte = buf[byte_index]

    with open(session["unprotected_path"], "wb") as f:
        f.write(buf)

    # Also flip same number in protected file (if it exists)
    prot_flips = []
    if session.get("protected_path"):
        info = read_protected_header(session["protected_path"])
        prot_flips = flip_random_bits(
            session["protected_path"], 1,
            region_start=info["header_len"]
        )

    flip_record = {
        "byte_index": byte_index,
        "bit_index": bit_index,
        "old_byte": old_byte,
        "new_byte": new_byte,
    }
    session["unprot_flip_history"].append(flip_record)
    session["prot_flip_history"].extend(prot_flips)
    session["total_flips_applied"] += 1
    session["state"]["corrupted"] = True

    return jsonify({
        "success": True,
        "old_byte": format(old_byte, "08b"),
        "new_byte": format(new_byte, "08b"),
        "total_flips": session["total_flips_applied"],
    })


# ---------------------------------------------------------------------------
# API: Compare ECC
# ---------------------------------------------------------------------------

@app.route("/api/compare-ecc", methods=["POST"])
def compare_ecc():
    if not session["original_path"]:
        return jsonify({"error": "No file selected"}), 400

    data = request.get_json(silent=True) or {}
    num_flips = data.get("num_flips", 5)
    num_flips = max(1, min(num_flips, 50))

    with open(session["original_path"], "rb") as f:
        file_data = f.read()

    # Cap data size for comparison (use first 8KB for speed)
    sample = file_data[:8192]
    results = compare_all(sample, num_flips, seed=random.randint(1, 999999))

    return jsonify({
        "success": True,
        "num_flips": num_flips,
        "sample_size": len(sample),
        "results": results,
    })


# ---------------------------------------------------------------------------
# API: Bit Grid Data
# ---------------------------------------------------------------------------

@app.route("/api/bit-grid/<file_type>")
def bit_grid(file_type):
    """Return a 512-byte window of the file as a bit array for canvas rendering, centering on corruption if present."""
    path_map = {
        "original": session.get("original_path"),
        "unprotected": session.get("unprotected_path"),
        "healed": session.get("healed_path"),
    }
    path = path_map.get(file_type)
    if not path or not os.path.exists(path):
        return jsonify({"error": f"File not available: {file_type}"}), 404

    # Calculate dynamic window start based on first flipped bit
    window_start = 0
    if session.get("unprot_flip_history"):
        first_flip = min(f["byte_index"] for f in session["unprot_flip_history"])
        # Align to 8-byte boundary (8 bytes = 64 bits = 1 row on canvas)
        window_start = (max(0, first_flip - 128) // 8) * 8

    max_bytes = 512  # 4096 bits
    file_size = os.path.getsize(path)
    
    # Adjust window if it exceeds file bounds
    if window_start + max_bytes > file_size:
        window_start = max(0, (file_size - max_bytes) // 8 * 8)

    with open(path, "rb") as f:
        f.seek(window_start)
        data = f.read(max_bytes)

    # Convert to bit array (list of 0/1)
    bits = []
    for byte in data:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)

    return jsonify({
        "file_type": file_type,
        "num_bytes": len(data),
        "total_file_bytes": file_size,
        "window_start": window_start,
        "bits": bits,
    })


# ---------------------------------------------------------------------------
# API: Corruption Heatmap
# ---------------------------------------------------------------------------

@app.route("/api/heatmap")
def heatmap():
    if not session["unprot_flip_history"]:
        return jsonify({"segments": [], "total_bytes": 0})

    total_bytes = session["original_size"]
    num_segments = min(64, total_bytes)
    segment_size = max(1, total_bytes // num_segments)

    segments = [0] * num_segments
    for flip in session["unprot_flip_history"]:
        idx = min(flip["byte_index"] // segment_size, num_segments - 1)
        segments[idx] += 1

    return jsonify({
        "segments": segments,
        "num_segments": num_segments,
        "segment_size": segment_size,
        "total_bytes": total_bytes,
        "total_flips": len(session["unprot_flip_history"]),
    })


# ---------------------------------------------------------------------------
# API: File Preview
# ---------------------------------------------------------------------------

@app.route("/api/file/<file_type>")
def file_preview(file_type):
    """Return file content for preview."""
    path_map = {
        "original": session.get("original_path"),
        "unprotected": session.get("unprotected_path"),
        "healed": session.get("healed_path"),
    }
    path = path_map.get(file_type)
    if not path or not os.path.exists(path):
        return jsonify({"error": f"File not available: {file_type}"}), 404

    kind = session.get("file_kind", "binary")

    if kind == "text":
        with open(path, "rb") as f:
            content = f.read().decode("utf-8", errors="replace")
        return jsonify({"kind": "text", "content": content})

    elif kind == "image":
        # Send the image file directly so the browser can render it
        return send_file(path, mimetype="application/octet-stream")

    else:
        with open(path, "rb") as f:
            head = f.read(256)
        return jsonify({
            "kind": "binary",
            "size": os.path.getsize(path),
            "hex_preview": head.hex(" "),
        })


@app.route("/api/file-image/<file_type>")
def file_image(file_type):
    """Serve an image file for <img> tags."""
    path_map = {
        "original": session.get("original_path"),
        "unprotected": session.get("unprotected_path"),
        "healed": session.get("healed_path"),
    }
    path = path_map.get(file_type)
    if not path or not os.path.exists(path):
        return "", 404
    return send_file(path)


# ---------------------------------------------------------------------------
# API: Status
# ---------------------------------------------------------------------------

@app.route("/api/status")
def status():
    return jsonify({
        "state": session["state"],
        "original_name": session["original_name"],
        "original_size": session["original_size"],
        "file_kind": session["file_kind"],
        "encoded_size": session["encoded_size"],
        "total_flips": session["total_flips_applied"],
        "errors_corrected": session["errors_corrected"],
        "hash_ok": session["hash_ok"],
        "corruption_rounds": session["corruption_rounds"],
        "integrity_timeline": session["integrity_timeline"],
        "original_hash": session["original_hash"],
    })


# ---------------------------------------------------------------------------
# API: Reset
# ---------------------------------------------------------------------------

@app.route("/api/reset", methods=["POST"])
def reset():
    _reset_session()
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# API: Export Report (PDF)
# ---------------------------------------------------------------------------

@app.route("/api/export-report")
def export_report():
    try:
        from fpdf import FPDF
    except ImportError:
        return jsonify({"error": "fpdf2 not installed. Run: pip install fpdf2"}), 500

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Title
    pdf.set_font("Helvetica", "B", 22)
    pdf.cell(0, 15, "BitRot Guard - Analysis Report", ln=True, align="C")
    pdf.ln(5)

    # Subtitle
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(120, 120, 120)
    pdf.cell(0, 8, f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", ln=True, align="C")
    pdf.cell(0, 8, "Hamming(7,4) Error-Correcting Code Demonstration", ln=True, align="C")
    pdf.ln(10)
    pdf.set_text_color(0, 0, 0)

    # File Info
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "1. File Information", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"  Filename: {session.get('original_name', 'N/A')}", ln=True)
    pdf.cell(0, 7, f"  File Type: {session.get('file_kind', 'N/A')}", ln=True)
    pdf.cell(0, 7, f"  Original Size: {session.get('original_size', 0):,} bytes", ln=True)
    pdf.cell(0, 7, f"  SHA-256: {session.get('original_hash', 'N/A')}", ln=True)
    pdf.ln(5)

    # Protection
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "2. Protection (Hamming 7,4 Encoding)", ln=True)
    pdf.set_font("Helvetica", "", 11)
    enc_size = session.get("encoded_size", 0)
    orig_size = session.get("original_size", 0)
    overhead = (enc_size / orig_size - 1) * 100 if orig_size else 0
    pdf.cell(0, 7, f"  Encoded Size: {enc_size:,} bytes", ln=True)
    pdf.cell(0, 7, f"  Overhead: {overhead:.1f}%", ln=True)
    pdf.cell(0, 7, "  Method: Each 4-bit nibble encoded as 7-bit codeword (3 parity bits)", ln=True)
    pdf.ln(5)

    # Corruption
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "3. Corruption Simulation", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"  Total Bit Flips Applied: {session.get('total_flips_applied', 0)}", ln=True)
    pdf.cell(0, 7, f"  Corruption Rounds: {session.get('corruption_rounds', 0)}", ln=True)
    pdf.ln(5)

    # Healing
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "4. Healing Results", ln=True)
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, f"  Errors Corrected: {session.get('errors_corrected', 0)}", ln=True)
    hash_ok = session.get("hash_ok")
    status_text = "PASS - Byte-for-byte identical" if hash_ok else ("FAIL - Hash mismatch" if hash_ok is False else "Not yet healed")
    pdf.cell(0, 7, f"  SHA-256 Verification: {status_text}", ln=True)
    pdf.ln(5)

    # Integrity Timeline
    timeline = session.get("integrity_timeline", [])
    if timeline:
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 10, "5. Integrity Timeline", ln=True)
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(60, 7, "Step", border=1)
        pdf.cell(50, 7, "Protected %", border=1)
        pdf.cell(50, 7, "Unprotected %", border=1)
        pdf.ln()
        pdf.set_font("Helvetica", "", 10)
        for entry in timeline:
            pdf.cell(60, 7, str(entry.get("step", "")), border=1)
            pdf.cell(50, 7, f"{entry.get('protected', 0):.2f}%", border=1)
            pdf.cell(50, 7, f"{entry.get('unprotected', 0):.2f}%", border=1)
            pdf.ln()
        pdf.ln(5)

    # Conclusion
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 10, "6. Conclusion", ln=True)
    pdf.set_font("Helvetica", "", 11)
    if hash_ok:
        pdf.multi_cell(0, 7,
            "The Hamming(7,4) error-correcting code successfully detected and corrected "
            "all single-bit errors in the protected file. The healed file is byte-for-byte "
            "identical to the original, verified by SHA-256 hash comparison. Meanwhile, the "
            "unprotected copy remains permanently corrupted with no possibility of recovery."
        )
    elif hash_ok is False:
        pdf.multi_cell(0, 7,
            "The Hamming(7,4) code was unable to fully recover the file. Some 7-bit blocks "
            "suffered 2 or more simultaneous bit flips, exceeding the code's single-error "
            "correction capability. Stronger codes (Reed-Solomon, LDPC) would be needed "
            "for this level of corruption."
        )
    else:
        pdf.multi_cell(0, 7,
            "The demonstration has not yet reached the healing step. Complete the full "
            "workflow (protect -> corrupt -> heal) to see the error correction in action."
        )

    # Save and send
    report_path = os.path.join(ARTIFACTS_DIR, "BitRotGuard_Report.pdf")
    pdf.output(report_path)
    return send_file(report_path, as_attachment=True, download_name="BitRotGuard_Report.pdf")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "0") == "1"
    print("\n" + "=" * 60)
    print("  BitRot Guard v3 — Web Interface")
    print(f"  Open http://localhost:{port} in your browser")
    print("=" * 60 + "\n")
    app.run(host="0.0.0.0", port=port, debug=debug)
