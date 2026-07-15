#!/usr/bin/env python3
"""
BitRot Guard
============
A single-file, pure-Python demonstration of protecting files against silent
bit-rot using a Hamming(7,4) error-correcting code — the same family of math
behind ECC memory and QR-code error correction.

Workflow: choose a file -> protect it (adds ECC redundancy) -> simulate
random bit flips ("bit rot") on both a protected copy and a plain unprotected
copy -> heal the protected copy and watch it recover perfectly, while the
unprotected copy stays broken.

The core tool (protect/corrupt/heal) is stdlib-only (tkinter). One extra
feature lights up automatically if numpy and matplotlib are installed: a
live Integrity Monitor graph tracking protected vs unprotected data over
the demo's timeline. Without them, the core tool still runs fine.

Run with a GUI:      python bitrot_guard.py
Run correctness test: python bitrot_guard.py --selftest
"""

import os
import sys
import shutil
import struct
import random
import difflib
import hashlib
import tkinter as tk
import tkinter.font as tkfont
from tkinter import filedialog, messagebox

try:
    import numpy as np
    import matplotlib

    matplotlib.use("TkAgg")
    from matplotlib.figure import Figure
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

    HAS_CHARTS = True
except ImportError:
    HAS_CHARTS = False

try:
    from PIL import Image, ImageTk

    HAS_PIL = True
except ImportError:
    HAS_PIL = False

MAGIC = b"BRG1"
ARTIFACTS_SUBDIR = "BitRotGuard_files"

# ---------------------------------------------------------------------------
# Hamming(7,4) core — single-error-correcting (SEC) code
#
# Each 4-bit data nibble (d1 d2 d3 d4) is encoded into a 7-bit codeword by
# adding 3 parity bits (p1 p2 p3), arranged at positions 1,2,4 of the
# codeword (1-indexed): [p1 p2 d1 p3 d2 d3 d4].
#
#   p1 = d1 ^ d2 ^ d4      (covers positions 1,3,5,7)
#   p2 = d1 ^ d3 ^ d4      (covers positions 2,3,6,7)
#   p3 = d2 ^ d3 ^ d4      (covers positions 4,5,6,7)
#
# On decode, recomputing the same three parity checks against the received
# bits yields a 3-bit "syndrome" whose value IS the 1-indexed position of the
# flipped bit (0 = no error) — the elegant property that makes Hamming codes
# self-locating. Flipping that bit back recovers the original nibble exactly,
# for any single-bit error per 7-bit block.
# ---------------------------------------------------------------------------


def _build_encode_table():
    table = []
    for nibble in range(16):
        d1 = (nibble >> 3) & 1
        d2 = (nibble >> 2) & 1
        d3 = (nibble >> 1) & 1
        d4 = nibble & 1
        p1 = d1 ^ d2 ^ d4
        p2 = d1 ^ d3 ^ d4
        p3 = d2 ^ d3 ^ d4
        bits = (p1, p2, d1, p3, d2, d3, d4)  # positions 1..7
        codeword = 0
        for b in bits:
            codeword = (codeword << 1) | b
        table.append(codeword)
    return table


def _build_decode_table():
    table = []
    for codeword in range(128):
        bits = [(codeword >> (6 - i)) & 1 for i in range(7)]  # positions 1..7
        r1, r2, r3, r4, r5, r6, r7 = bits
        s1 = r1 ^ r3 ^ r5 ^ r7
        s2 = r2 ^ r3 ^ r6 ^ r7
        s3 = r4 ^ r5 ^ r6 ^ r7
        syndrome = s1 | (s2 << 1) | (s3 << 2)
        corrected = bits[:]
        if syndrome != 0:
            corrected[syndrome - 1] ^= 1
        d1, d2, d3, d4 = corrected[2], corrected[4], corrected[5], corrected[6]
        nibble = (d1 << 3) | (d2 << 2) | (d3 << 1) | d4
        table.append((nibble, 1 if syndrome else 0))
    return table


ENCODE_TABLE = _build_encode_table()
DECODE_TABLE = _build_decode_table()


def hamming_encode_bytes(data: bytes) -> bytes:
    bit_buffer = 0
    bit_count = 0
    out = bytearray()
    for byte in data:
        for nibble in (byte >> 4, byte & 0xF):
            codeword = ENCODE_TABLE[nibble]
            bit_buffer = (bit_buffer << 7) | codeword
            bit_count += 7
            while bit_count >= 8:
                bit_count -= 8
                out.append((bit_buffer >> bit_count) & 0xFF)
                bit_buffer &= (1 << bit_count) - 1
    if bit_count > 0:
        out.append((bit_buffer << (8 - bit_count)) & 0xFF)
    return bytes(out)


def hamming_decode_bytes(data: bytes, original_size: int):
    num_nibbles = original_size * 2
    bit_buffer = 0
    bit_count = 0
    out = bytearray()
    errors_corrected = 0
    nibbles_done = 0
    pending_high = None
    for byte in data:
        bit_buffer = (bit_buffer << 8) | byte
        bit_count += 8
        while bit_count >= 7 and nibbles_done < num_nibbles:
            bit_count -= 7
            codeword = (bit_buffer >> bit_count) & 0x7F
            bit_buffer &= (1 << bit_count) - 1
            nibble, err = DECODE_TABLE[codeword]
            errors_corrected += err
            nibbles_done += 1
            if pending_high is None:
                pending_high = nibble
            else:
                out.append((pending_high << 4) | nibble)
                pending_high = None
        if nibbles_done >= num_nibbles:
            break
    return bytes(out), errors_corrected


# ---------------------------------------------------------------------------
# .hprot file format:  MAGIC(4) | version(1) | name_len(2) | name |
#                      original_size(8) | sha256(32) | hamming-encoded data
# ---------------------------------------------------------------------------


def protect_file(input_path, output_path):
    with open(input_path, "rb") as f:
        data = f.read()
    original_size = len(data)
    digest = hashlib.sha256(data).digest()
    encoded = hamming_encode_bytes(data)
    name = os.path.basename(input_path).encode("utf-8")
    with open(output_path, "wb") as f:
        f.write(MAGIC)
        f.write(struct.pack(">B", 1))
        f.write(struct.pack(">H", len(name)))
        f.write(name)
        f.write(struct.pack(">Q", original_size))
        f.write(digest)
        f.write(encoded)
    return output_path, original_size, len(encoded)


def read_protected_header(path):
    with open(path, "rb") as f:
        magic = f.read(4)
        if magic != MAGIC:
            raise ValueError("Not a valid BitRot Guard (.hprot) file")
        struct.unpack(">B", f.read(1))[0]  # version, unused
        name_len = struct.unpack(">H", f.read(2))[0]
        name = f.read(name_len).decode("utf-8")
        original_size = struct.unpack(">Q", f.read(8))[0]
        digest = f.read(32)
        header_len = f.tell()
        encoded = f.read()
    return {
        "name": name,
        "original_size": original_size,
        "sha256": digest,
        "header_len": header_len,
        "encoded": encoded,
    }


def heal_file(protected_path, output_path):
    info = read_protected_header(protected_path)
    recovered, errors_corrected = hamming_decode_bytes(info["encoded"], info["original_size"])
    ok = hashlib.sha256(recovered).digest() == info["sha256"]
    with open(output_path, "wb") as f:
        f.write(recovered)
    return output_path, errors_corrected, ok


def flip_random_bits(path, num_bits, region_start=0, region_end=None, seed=None):
    """Simulate bit-rot: flip `num_bits` random bits within [region_start, region_end)."""
    with open(path, "rb") as f:
        data = bytearray(f.read())
    if region_end is None:
        region_end = len(data)
    total_bits = (region_end - region_start) * 8
    num_bits = min(num_bits, total_bits)
    rng = random.Random(seed)
    chosen = rng.sample(range(total_bits), num_bits)
    flipped = []
    for bitpos in chosen:
        byte_index = region_start + bitpos // 8
        bit_index = bitpos % 8
        old_byte = data[byte_index]
        data[byte_index] ^= (1 << (7 - bit_index))
        flipped.append(
            {
                "byte_index": byte_index,
                "bit_index": bit_index,
                "old_byte": old_byte,
                "new_byte": data[byte_index],
            }
        )
    with open(path, "wb") as f:
        f.write(data)
    return flipped


# ---------------------------------------------------------------------------
# Byte-level diff — used by the Integrity Monitor to compute real integrity
# percentages. Pure function, only exercised when HAS_CHARTS.
# ---------------------------------------------------------------------------


def byte_diff_mask(reference: bytes, other: bytes):
    n = min(len(reference), len(other))
    ref = np.frombuffer(reference[:n], dtype=np.uint8)
    oth = np.frombuffer(other[:n], dtype=np.uint8)
    return ref != oth


def detect_kind(path):
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
        head.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        pass
    if HAS_PIL:
        try:
            with Image.open(path) as im:
                im.verify()
            return "image"
        except Exception:
            return "binary"
    try:
        tk.PhotoImage(file=path)
        return "image"
    except Exception:
        return "binary"


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------


def _selftest():
    import secrets

    data = secrets.token_bytes(4096)
    encoded = bytearray(hamming_encode_bytes(data))
    num_blocks = len(data) * 2
    rng = random.Random(42)
    tested_blocks = set()
    flips = 0
    target_flips = 50
    while flips < target_flips:
        block = rng.randrange(num_blocks)
        if block in tested_blocks:
            continue
        tested_blocks.add(block)
        bit_in_block = rng.randrange(7)
        global_bit = block * 7 + bit_in_block
        byte_idx, bit_idx = divmod(global_bit, 8)
        encoded[byte_idx] ^= (1 << (7 - bit_idx))
        flips += 1
    recovered, corrected = hamming_decode_bytes(bytes(encoded), len(data))
    assert recovered == data, "Self-test FAILED: recovered data does not match original!"
    assert corrected == flips, f"Self-test FAILED: expected {flips} corrections, got {corrected}"
    print(
        f"Self-test PASSED: {flips} single-bit errors injected across "
        f"{num_blocks} independent 7-bit blocks, all corrected, "
        f"data recovered byte-for-byte identical."
    )


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Color palette (dark theme)
# ---------------------------------------------------------------------------
BG = "#1e1f2b"
BG_PANEL = "#262837"
BG_INSET = "#1a1b25"
BORDER = "#3a3d54"
SHADOW = "#111219"
FG = "#f0f0f5"
MUTED = "#8890b5"
BLUE = "#66d9ef"
PURPLE = "#bd93f9"
GREEN = "#50fa7b"
ORANGE = "#ffb86c"
RED = "#ff5c5c"
PINK = "#ff79c6"


def style_dark_axes(fig, ax):
    """Make a matplotlib Axes match the app's dark theme instead of the
    default white-background look."""
    fig.patch.set_facecolor(BG_INSET)
    ax.set_facecolor(BG_INSET)
    for spine in ax.spines.values():
        spine.set_color(BORDER)
    ax.tick_params(colors=MUTED, labelsize=8)
    ax.title.set_color(FG)
    ax.xaxis.label.set_color(MUTED)
    ax.yaxis.label.set_color(MUTED)
    ax.grid(True, color=BORDER, alpha=0.25, linewidth=0.6)


def _rounded_points(x1, y1, x2, y2, radius):
    return [
        x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
        x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
        x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
    ]


def _lighten(hex_color, amount=22):
    hex_color = hex_color.lstrip("#")
    r, g, b = (int(hex_color[i : i + 2], 16) for i in (0, 2, 4))
    r, g, b = (min(255, c + amount) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


class RoundedButton(tk.Canvas):
    """A pill-shaped, hover-lit button drawn on a Canvas — ttk buttons can't
    do rounded corners, and rounded corners are the single biggest visual
    cue that separates a modern web-app look from a plain desktop toolbar."""

    def __init__(
        self,
        parent,
        text,
        command=None,
        bg=PURPLE,
        fg=None,
        font=("Segoe UI", 10, "bold"),
        height=40,
        radius=18,
        padx=22,
        state="normal",
        parent_bg=BG,
    ):
        self._font = font
        font_obj = tkfont.Font(font=font)
        width = font_obj.measure(text) + padx * 2
        super().__init__(parent, width=width, height=height, bg=parent_bg, highlightthickness=0, bd=0)
        self.command = command
        self.bg_color = bg
        self.fg_color = fg or BG_INSET
        self.text = text
        self.radius = radius
        self.width = width
        self.height = height
        self._state = state
        self._hover = False
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda e: self._set_hover(True))
        self.bind("<Leave>", lambda e: self._set_hover(False))
        self._draw()

    def _draw(self):
        self.delete("all")
        disabled = self._state == "disabled"
        fill = BORDER if disabled else (_lighten(self.bg_color) if self._hover else self.bg_color)
        fg = MUTED if disabled else self.fg_color
        self.create_polygon(
            _rounded_points(1, 1, self.width - 1, self.height - 1, self.radius),
            smooth=True,
            fill=fill,
            outline="",
        )
        self.create_text(self.width // 2, self.height // 2, text=self.text, fill=fg, font=self._font)
        self.configure(cursor="hand2" if not disabled else "arrow")

    def _set_hover(self, is_hover):
        if self._state != "disabled":
            self._hover = is_hover
            self._draw()

    def _on_click(self, _event):
        if self._state != "disabled" and self.command:
            self.command()

    def set_state(self, state):
        self._state = state
        self._hover = False
        self._draw()


def make_card(parent, bg=BG_PANEL):
    """A frame with a subtle drop-shadow illusion (an offset darker frame
    peeking out behind it) — the other big visual cue for a web-app look."""
    shadow = tk.Frame(parent, bg=SHADOW)
    card = tk.Frame(shadow, bg=bg)
    card.pack(fill="both", expand=True, padx=(0, 4), pady=(0, 4))
    return shadow, card


def make_chip(parent, text, bg, fg, font=("Segoe UI", 9, "bold")):
    font_obj = tkfont.Font(font=font)
    w = font_obj.measure(text) + 24
    h = 26
    chip = tk.Canvas(parent, width=w, height=h, bg=parent.cget("bg"), highlightthickness=0, bd=0)
    chip.create_polygon(_rounded_points(1, 1, w - 1, h - 1, h // 2), smooth=True, fill=bg, outline="")
    chip.create_text(w // 2, h // 2, text=text, fill=fg, font=font)
    return chip


class IntegrityMonitor(tk.Frame):
    """A small embedded, animated area chart tracking data integrity over
    the demo's timeline — protected vs unprotected — ticking like a
    heart-rate monitor as each step happens, snapping back to 100% on heal."""

    def __init__(self, parent, bg=BG_PANEL):
        super().__init__(parent, bg=bg)
        self.fig = Figure(figsize=(10.2, 2.0), dpi=100)
        self.ax = self.fig.add_subplot(111)
        self.canvas = FigureCanvasTkAgg(self.fig, master=self)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self._reset_lines()
        self._redraw()

    def _reset_lines(self):
        self.events = [(0, "Start")]
        self.unprotected_ys = [100.0]
        self.protected_ys = [100.0]

    def reset(self):
        self._reset_lines()
        self._redraw()

    def checkpoint(self, label, unprotected_pct, protected_pct, animate=True):
        self.events.append((self.events[-1][0] + 1, label))
        if animate:
            self._animate_to(unprotected_pct, protected_pct)
        else:
            self.unprotected_ys.append(unprotected_pct)
            self.protected_ys.append(protected_pct)
            self._redraw()

    def _animate_to(self, target_unprot, target_prot, steps=12, delay=16):
        start_u = self.unprotected_ys[-1]
        start_p = self.protected_ys[-1]
        self.unprotected_ys.append(start_u)
        self.protected_ys.append(start_p)

        def step(i):
            t = i / steps
            self.unprotected_ys[-1] = start_u + (target_unprot - start_u) * t
            self.protected_ys[-1] = start_p + (target_prot - start_p) * t
            self._redraw()
            if i < steps:
                self.after(delay, lambda: step(i + 1))

        step(0)

    def _redraw(self):
        self.ax.clear()
        style_dark_axes(self.fig, self.ax)
        xs = [e[0] for e in self.events]
        labels = [e[1] for e in self.events]

        self.ax.fill_between(xs, self.unprotected_ys, 0, color=RED, alpha=0.12, zorder=1)
        self.ax.fill_between(xs, self.protected_ys, 0, color=GREEN, alpha=0.12, zorder=1)
        self.ax.plot(
            xs, self.unprotected_ys, color=RED, marker="o", markersize=5, linewidth=2.4,
            label="Unprotected", zorder=3,
        )
        self.ax.plot(
            xs, self.protected_ys, color=GREEN, marker="o", markersize=5, linewidth=2.4,
            label="Protected", zorder=3,
        )

        # Auto-zoom the y-axis to the actual data range so even a tiny dip (e.g.
        # a handful of corrupted bytes in a big file) still reads as a visible
        # drop. Padding is a fraction of the observed span, not a fixed floor —
        # a fixed floor (old code capped ymin at 96) flattens a 0.05% dip into
        # an invisible sliver, making the red line look "fully healed" when
        # it's actually still broken.
        vals = self.unprotected_ys + self.protected_ys
        low, high = min(vals), max(vals)
        span = high - low
        pad = max(span * 0.25, 0.15)
        ymin = max(-2, low - pad)
        ymax = min(103, high + pad)
        self.ax.set_ylim(ymin, ymax)
        self.ax.set_xticks(xs)
        self.ax.set_xticklabels(labels, fontsize=9)
        self.ax.set_ylabel("Integrity %", fontsize=9)
        self.ax.legend(
            loc="lower left", fontsize=8, facecolor=BG_INSET, edgecolor=BORDER, labelcolor=FG, framealpha=0.9
        )
        self.fig.tight_layout(pad=0.6)
        self.canvas.draw_idle()


class BitRotGuardApp(tk.Tk):
    PREVIEW_MAX = 320

    def __init__(self):
        super().__init__()
        self.title("BitRot Guard — Hamming Code File Protection Demo")
        self.geometry("1100x980")
        self.minsize(960, 850)
        self.configure(bg=BG)

        self.original_path = None
        self.protected_path = None
        self.unprotected_path = None
        self.healed_path = None
        self.output_dir = None
        self.kind = None
        self.unprot_flip_history = []
        self.prot_flip_history = []
        self._last_unprotected_pct = None
        self.state = dict(chosen=False, protected=False, corrupted=False, healed=False, healed_ok=None)

        self._build_ui()
        self.log(
            "Welcome to BitRot Guard.\n"
            "1) Choose a file.  2) Protect it (adds Hamming(7,4) ECC redundancy).\n"
            "3) Simulate random bit flips ('bit rot') on both copies.  4) Heal the protected copy.\n"
            + (
                "Tip: for the clearest visual demo use a .txt file, or a .jpg/.png/.bmp/.gif image."
                if HAS_PIL
                else "Tip: for the clearest visual demo use a .txt, .png, .gif, or .ppm/.pgm image — "
                "install Pillow (pip install pillow) to also preview JPG/BMP/WEBP."
            ),
            "info",
        )

    def _build_ui(self):
        # --- Header ---
        header = tk.Frame(self, bg=BG)
        header.pack(fill="x", padx=28, pady=(24, 18))
        tk.Label(header, text="🛡️  BitRot Guard", bg=BG, fg=FG, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(
            header,
            text="Hamming-code self-healing file protection — detect, correct, and prove it.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(3, 0))

        # --- Control card: file chooser + action buttons + status chips ---
        ctrl_shadow, ctrl_card = make_card(self)
        ctrl_shadow.pack(fill="x", padx=28, pady=(0, 18))

        file_row = tk.Frame(ctrl_card, bg=BG_PANEL)
        file_row.pack(fill="x", padx=20, pady=(20, 12))
        self.choose_btn = RoundedButton(
            file_row, "📁  Choose File", command=self.choose_file, bg=BLUE, parent_bg=BG_PANEL
        )
        self.choose_btn.pack(side="left")
        self.file_label = tk.Label(
            file_row, text="No file selected", bg=BG_PANEL, fg=MUTED, font=("Segoe UI", 10)
        )
        self.file_label.pack(side="left", padx=16)

        btn_row = tk.Frame(ctrl_card, bg=BG_PANEL)
        btn_row.pack(fill="x", padx=20, pady=(0, 16))
        self.protect_btn = RoundedButton(
            btn_row, "🛡️  Protect File", command=self.do_protect, bg=PURPLE, parent_bg=BG_PANEL, state="disabled"
        )
        self.protect_btn.pack(side="left")
        self.corrupt_btn = RoundedButton(
            btn_row,
            "💥  Simulate Bit Rot",
            command=self.do_corrupt,
            bg=ORANGE,
            parent_bg=BG_PANEL,
            state="disabled",
        )
        self.corrupt_btn.pack(side="left", padx=10)
        self.heal_btn = RoundedButton(
            btn_row, "✨  Heal / Recover", command=self.do_heal, bg=GREEN, parent_bg=BG_PANEL, state="disabled"
        )
        self.heal_btn.pack(side="left")
        self.reset_btn = RoundedButton(
            btn_row, "⟲  Reset", command=lambda: self.reset(keep_choice=False), bg=RED, parent_bg=BG_PANEL
        )
        self.reset_btn.pack(side="left", padx=(24, 0))

        self.status_row = tk.Frame(ctrl_card, bg=BG_PANEL)
        self.status_row.pack(fill="x", padx=20, pady=(0, 20))
        self.update_status()

        # --- Integrity monitor card (the one graph) ---
        if HAS_CHARTS:
            chart_shadow, chart_card = make_card(self)
            chart_shadow.pack(fill="x", padx=28, pady=(0, 18))
            tk.Label(
                chart_card, text="📈  Integrity Over Time", bg=BG_PANEL, fg=PURPLE, font=("Segoe UI", 11, "bold")
            ).pack(anchor="w", padx=18, pady=(14, 0))
            self.integrity_monitor = IntegrityMonitor(chart_card, bg=BG_PANEL)
            self.integrity_monitor.pack(fill="both", expand=True, padx=14, pady=(4, 14))
        else:
            self.integrity_monitor = None

        # --- Preview panels ---
        prev = tk.Frame(self, bg=BG)
        prev.pack(fill="both", expand=True, padx=28, pady=(0, 18))
        self.panels = {}
        self.panel_title_labels = {}
        self.panel_titles = {
            "original": "📄  Original",
            "unprotected": "☠️  Unprotected (no ECC)",
            "healed": "✅  Protected → Healed",
        }
        for i, key in enumerate(("original", "unprotected", "healed")):
            shadow, card = make_card(prev)
            shadow.grid(row=0, column=i, sticky="nsew", padx=6)
            prev.columnconfigure(i, weight=1)
            prev.rowconfigure(0, weight=1)
            title_lbl = tk.Label(
                card, text=self.panel_titles[key], bg=BG_PANEL, fg=PURPLE, font=("Segoe UI", 11, "bold"), anchor="w"
            )
            title_lbl.pack(fill="x", padx=16, pady=(14, 8))
            content = tk.Frame(card, bg=BG_PANEL)
            content.pack(fill="both", expand=True, padx=12, pady=(0, 14))
            self.panels[key] = content
            self.panel_title_labels[key] = title_lbl
            tk.Label(content, text="(not yet created)", bg=BG_PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(pady=40)

        # --- Log card ---
        log_shadow, log_card = make_card(self)
        log_shadow.pack(fill="both", expand=False, padx=28, pady=(0, 28))
        tk.Label(
            log_card, text="📜  Activity Log", bg=BG_PANEL, fg=PURPLE, font=("Segoe UI", 11, "bold"), anchor="w"
        ).pack(fill="x", padx=18, pady=(14, 8))
        self.log_text = tk.Text(
            log_card,
            height=7,
            state="disabled",
            font=("Consolas", 9),
            wrap="word",
            bg=BG_INSET,
            fg=FG,
            insertbackground=FG,
            selectbackground=BORDER,
            relief="flat",
            padx=10,
            pady=8,
        )
        self.log_text.pack(fill="both", expand=True, padx=14, pady=(0, 16))
        self.log_text.tag_configure("info", foreground=BLUE)
        self.log_text.tag_configure("success", foreground=GREEN)
        self.log_text.tag_configure("warning", foreground=ORANGE)
        self.log_text.tag_configure("error", foreground=RED)
        self.log_text.tag_configure("muted", foreground=MUTED)
        self.log_text.tag_configure("bit_bad", background=RED, foreground=BG_INSET, font=("Consolas", 9, "bold"))
        self.log_text.tag_configure(
            "bit_fixed", background=GREEN, foreground=BG_INSET, font=("Consolas", 9, "bold")
        )

    def log(self, msg, tag="info"):
        self.log_text.configure(state="normal")
        self.log_text.insert("end", msg + "\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def log_bit_flip(self, label, flip, bit_tag="bit_bad"):
        """Log one flipped bit as an 8-bit binary before/after, with the
        actual flipped bit highlighted so you can see exactly which bit rotted."""
        old_bits = format(flip["old_byte"], "08b")
        new_bits = format(flip["new_byte"], "08b")
        diff_pos = next(i for i in range(8) if old_bits[i] != new_bits[i])
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"    {label} byte {flip['byte_index']}:  ", "muted")
        self.log_text.insert("end", old_bits, "muted")
        self.log_text.insert("end", "  ->  ", "muted")
        self.log_text.insert("end", new_bits[:diff_pos], "muted")
        self.log_text.insert("end", new_bits[diff_pos], bit_tag)
        self.log_text.insert("end", new_bits[diff_pos + 1 :] + "\n", "muted")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.update_idletasks()

    def update_status(self):
        for child in self.status_row.winfo_children():
            child.destroy()
        s = self.state
        chips = [
            ("File chosen", s["chosen"], BLUE),
            ("Protected", s["protected"], PURPLE),
            ("Bit-rot simulated", s["corrupted"], ORANGE),
        ]
        if s["healed"]:
            chips.append(
                ("Healed — perfect recovery", True, GREEN)
                if s["healed_ok"]
                else ("Healed — hash mismatch", True, RED)
            )
        else:
            chips.append(("Healed", False, GREEN))
        for text, active, color in chips:
            mark = "✓ " if active else "○ "
            bg = color if active else BORDER
            fg = BG_INSET if active else MUTED
            chip = make_chip(self.status_row, mark + text, bg, fg)
            chip.pack(side="left", padx=(0, 8))

    def choose_file(self):
        path = filedialog.askopenfilename(title="Choose a file to protect")
        if not path:
            return
        self.reset(keep_choice=False)
        self.original_path = path
        self.output_dir = os.path.dirname(path)
        self.kind = detect_kind(path)
        self.file_label.configure(text=os.path.basename(path))
        self.log(f"Selected: {path}  (detected as {self.kind})", "info")
        self.state["chosen"] = True
        self.protect_btn.set_state("normal")
        self.render_panel("original", path)
        self.update_status()

    def _handle_write_failure(self, error):
        """On a blocked write (e.g. Windows Controlled Folder Access protecting
        Documents/Desktop from unrecognized apps), ask the user for a different,
        writable output folder instead of just dying with a raw traceback."""
        self.log(
            f"⚠ Couldn't write to '{self.output_dir}' ({error}). "
            f"That folder may be protected (e.g. Windows Controlled Folder Access) "
            f"or you may lack permission there.",
            "error",
        )
        messagebox.showwarning(
            "Write blocked",
            f"Couldn't create files in:\n{self.output_dir}\n\n"
            "This folder may be protected by Windows (Controlled Folder Access under "
            "Virus & threat protection > Ransomware protection) or you may lack write "
            "permission there.\n\nChoose a different folder to save the protected files.",
        )
        new_dir = filedialog.askdirectory(title="Choose a writable output folder", initialdir=self.output_dir)
        if not new_dir:
            return False
        self._relocate_outputs(new_dir)
        self.output_dir = new_dir
        self.log(f"Retrying with output folder: {new_dir}", "info")
        return True

    def _relocate_outputs(self, new_dir):
        """Move any already-created protected/unprotected/healed files into a
        freshly chosen writable folder, so an in-place step (like corrupting
        bits in an existing file) keeps working if Windows blocks the folder
        those files were originally created in partway through the demo."""
        new_artifacts_dir = os.path.join(new_dir, ARTIFACTS_SUBDIR)
        for attr in ("protected_path", "unprotected_path", "healed_path"):
            old_path = getattr(self, attr)
            if old_path and os.path.exists(old_path):
                try:
                    os.makedirs(new_artifacts_dir, exist_ok=True)
                    new_path = os.path.join(new_artifacts_dir, os.path.basename(old_path))
                    shutil.move(old_path, new_path)
                    setattr(self, attr, new_path)
                except OSError:
                    pass

    def _artifacts_dir(self):
        """Generated files live in a small subfolder next to the original
        file, instead of the OS 'hidden' attribute — marking a file hidden
        and then repeatedly rewriting it (as bit-flip simulation does) reads
        as ransomware-like behavior to Windows' behavior-monitoring defenses
        and can get the whole process's file access blocked."""
        d = os.path.join(self.output_dir, ARTIFACTS_SUBDIR)
        os.makedirs(d, exist_ok=True)
        return d

    def do_protect(self):
        base = os.path.basename(self.original_path)
        name, ext = os.path.splitext(base)
        while True:
            try:
                artifacts_dir = self._artifacts_dir()
                protected_path = os.path.join(artifacts_dir, f"{name}_protected.hprot")
                unprotected_path = os.path.join(artifacts_dir, f"{name}_unprotected{ext}")
                _, orig_size, enc_size = protect_file(self.original_path, protected_path)
                with open(self.original_path, "rb") as fsrc, open(unprotected_path, "wb") as fdst:
                    fdst.write(fsrc.read())
                self.protected_path = protected_path
                self.unprotected_path = unprotected_path
                break
            except OSError as e:
                if self._handle_write_failure(e):
                    continue
                return

        overhead = (enc_size / orig_size - 1) * 100 if orig_size else 0
        self.log(
            f"Protected: {orig_size} bytes -> {enc_size} bytes of Hamming(7,4) ECC data "
            f"(+{overhead:.0f}% overhead) -> {ARTIFACTS_SUBDIR}/{os.path.basename(self.protected_path)}",
            "success",
        )
        self.log(
            f"Unprotected reference copy saved: {ARTIFACTS_SUBDIR}/{os.path.basename(self.unprotected_path)}",
            "info",
        )
        self.state["protected"] = True
        self.unprot_flip_history = []
        self.prot_flip_history = []
        self.corrupt_btn.set_state("normal")
        self.render_panel("unprotected", self.unprotected_path)
        self.update_status()
        if self.integrity_monitor:
            self.integrity_monitor.checkpoint("Protected", 100, 100)

    MAX_LOGGED_FLIPS = 15
    MIN_RANDOM_FLIPS = 3
    MAX_RANDOM_FLIPS = 7

    def do_corrupt(self):
        n = random.randint(self.MIN_RANDOM_FLIPS, self.MAX_RANDOM_FLIPS)
        while True:
            try:
                info = read_protected_header(self.protected_path)
                prot_flips = flip_random_bits(self.protected_path, n, region_start=info["header_len"])
                unprot_flips = flip_random_bits(self.unprotected_path, n)
                break
            except OSError as e:
                if self._handle_write_failure(e):
                    continue
                return

        self.prot_flip_history.extend(prot_flips)
        self.unprot_flip_history.extend(unprot_flips)

        self.log(
            "💥 Bit rot is silently corrupting both copies... "
            "(real bit rot gives no warning and no error count — heal to find out what happened)",
            "warning",
        )

        self.state["corrupted"] = True
        self.render_panel("unprotected", self.unprotected_path, reference_path=self.original_path)
        self.heal_btn.set_state("normal")
        self.update_status()

        if HAS_CHARTS:
            with open(self.original_path, "rb") as f:
                orig_bytes = f.read()
            with open(self.unprotected_path, "rb") as f:
                unprot_bytes = f.read()
            self._last_unprotected_pct = 100.0 * (1 - float(np.mean(byte_diff_mask(orig_bytes, unprot_bytes))))
            if self.integrity_monitor:
                self.integrity_monitor.checkpoint("Corrupted", self._last_unprotected_pct, 100)

    def do_heal(self):
        base = os.path.basename(self.original_path)
        name, ext = os.path.splitext(base)
        while True:
            try:
                artifacts_dir = self._artifacts_dir()
                healed_path = os.path.join(artifacts_dir, f"{name}_healed{ext}")
                _, errors_corrected, ok = heal_file(self.protected_path, healed_path)
                self.healed_path = healed_path
                break
            except OSError as e:
                if self._handle_write_failure(e):
                    continue
                return

        self.log("🔍 Revealing what actually happened during bit rot:", "info")
        self.log(f"    {len(self.unprot_flip_history)} bit(s) rotted on the unprotected copy:", "muted")
        for flip in self.unprot_flip_history[: self.MAX_LOGGED_FLIPS]:
            self.log_bit_flip("rotted", flip, bit_tag="bit_bad")
        if len(self.unprot_flip_history) > self.MAX_LOGGED_FLIPS:
            self.log(f"    ... and {len(self.unprot_flip_history) - self.MAX_LOGGED_FLIPS} more", "muted")

        self.log(f"    {len(self.prot_flip_history)} bit(s) rotted inside the protected copy's ECC data:", "muted")
        for flip in self.prot_flip_history[: self.MAX_LOGGED_FLIPS]:
            self.log_bit_flip("rotted", flip, bit_tag="bit_fixed")
        if len(self.prot_flip_history) > self.MAX_LOGGED_FLIPS:
            self.log(f"    ... and {len(self.prot_flip_history) - self.MAX_LOGGED_FLIPS} more", "muted")

        if ok:
            self.log(
                f"✅ Healed successfully — {errors_corrected} bit error(s) detected & corrected. "
                f"SHA-256 matches the original exactly. "
                f"Saved as {ARTIFACTS_SUBDIR}/{os.path.basename(self.healed_path)}",
                "success",
            )
        else:
            self.log(
                f"⚠ Healed file does NOT match the original hash — {errors_corrected} correction(s) "
                f"made, but some 7-bit blocks likely took 2+ simultaneous flips, beyond what "
                f"Hamming(7,4) can guarantee to fix. Try again.",
                "error",
            )
        self.state["healed"] = True
        self.state["healed_ok"] = ok
        self.render_panel("healed", self.healed_path, reference_path=self.unprotected_path)
        self.update_status()

        if HAS_CHARTS and self.integrity_monitor:
            with open(self.original_path, "rb") as f:
                orig_bytes = f.read()
            with open(self.healed_path, "rb") as f:
                healed_bytes = f.read()
            protected_pct = 100.0 * (1 - float(np.mean(byte_diff_mask(orig_bytes, healed_bytes))))
            unprot_pct = self._last_unprotected_pct if self._last_unprotected_pct is not None else 0.0
            self.integrity_monitor.checkpoint("Healed", unprot_pct, protected_pct)

    @staticmethod
    def _expand_to_word(content, start, end):
        """Grow a character diff range out to its enclosing word so the
        highlight reads as a visible chunk instead of a single faint pixel."""
        while start > 0 and not content[start - 1].isspace():
            start -= 1
        while end < len(content) and not content[end].isspace():
            end += 1
        return start, end

    def render_panel(self, key, path, reference_path=None):
        frame = self.panels[key]
        for w in frame.winfo_children():
            w.destroy()
        if not path or not os.path.exists(path):
            self.panel_title_labels[key].configure(text=self.panel_titles[key])
            tk.Label(frame, text="(not yet created)", bg=BG_PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(pady=40)
            return
        if self.kind == "text":
            # Decode with errors="replace" (never raises) so corrupted byte
            # sequences always render as visible "�" gibberish instead of
            # sometimes succeeding and sometimes bailing to a placeholder —
            # consistent behavior regardless of where the bits happened to land.
            with open(path, "rb") as f:
                content = f.read().decode("utf-8", errors="replace")
            txt = tk.Text(
                frame,
                wrap="word",
                height=13,
                width=24,
                font=("Consolas", 10),
                bg=BG_INSET,
                fg=FG,
                insertbackground=FG,
                selectbackground=BORDER,
                relief="flat",
                padx=8,
                pady=8,
            )
            txt.insert("1.0", content)
            self.panel_title_labels[key].configure(text=self.panel_titles[key])
            if reference_path and os.path.exists(reference_path):
                is_fixed = key == "healed"
                tagname = "diff_fixed" if is_fixed else "diff_bad"
                txt.tag_configure(
                    tagname,
                    background=(GREEN if is_fixed else RED),
                    foreground=BG_INSET,
                    font=("Consolas", 10, "bold"),
                    relief="solid",
                    borderwidth=2,
                    underline=True,
                )
                with open(reference_path, "rb") as rf:
                    reference_content = rf.read().decode("utf-8", errors="replace")
                matcher = difflib.SequenceMatcher(None, reference_content, content, autojunk=False)
                diff_chars = 0
                for op, _a0, _a1, b0, b1 in matcher.get_opcodes():
                    if op != "equal" and b1 > b0:
                        diff_chars += b1 - b0
                        w0, w1 = self._expand_to_word(content, b0, b1)
                        txt.tag_add(tagname, f"1.0+{w0}c", f"1.0+{w1}c")
                if diff_chars:
                    verb = "auto-corrected" if is_fixed else "corrupted"
                    icon = "✅" if is_fixed else "⚠"
                    self.panel_title_labels[key].configure(
                        text=f"{self.panel_titles[key]}  —  {icon} {diff_chars} char(s) {verb}"
                    )
            txt.configure(state="disabled")
            txt.pack(fill="both", expand=True)
        elif self.kind == "image":
            try:
                if HAS_PIL:
                    # Pillow decodes JPG/PNG/BMP/WEBP/etc — needed because
                    # tk.PhotoImage only understands PNG/GIF/PPM/PGM natively.
                    pil_img = Image.open(path)
                    pil_img.load()
                    if pil_img.mode not in ("RGB", "RGBA"):
                        pil_img = pil_img.convert("RGBA")
                    pil_img.thumbnail((self.PREVIEW_MAX, self.PREVIEW_MAX), Image.LANCZOS)
                    img = ImageTk.PhotoImage(pil_img)
                else:
                    img = tk.PhotoImage(file=path)
                    factor = max(1, max(img.width(), img.height()) // self.PREVIEW_MAX)
                    if factor > 1:
                        img = img.subsample(factor, factor)
                holder = tk.Frame(frame, bg=BG_INSET)
                holder.pack(fill="both", expand=True)
                lbl = tk.Label(holder, image=img, bg=BG_INSET)
                lbl.image = img  # keep a reference alive
                lbl.pack(pady=14)
            except Exception:
                tk.Label(
                    frame,
                    text="❌ Image failed to load —\nfile is corrupted!",
                    fg=RED,
                    bg=BG_PANEL,
                    font=("Segoe UI", 10, "bold"),
                    justify="center",
                ).pack(pady=40)
        else:
            size = os.path.getsize(path)
            with open(path, "rb") as f:
                head = f.read(64)
            tk.Label(
                frame,
                text=f"Binary file, {size} bytes\nFirst bytes:\n{head.hex(' ')}",
                font=("Consolas", 8),
                fg=MUTED,
                bg=BG_PANEL,
                wraplength=280,
                justify="left",
            ).pack(pady=10)

    def reset(self, keep_choice=True):
        self.protected_path = None
        self.unprotected_path = None
        self.healed_path = None
        self.unprot_flip_history = []
        self.prot_flip_history = []
        self._last_unprotected_pct = None
        self.state["protected"] = False
        self.state["corrupted"] = False
        self.state["healed"] = False
        self.state["healed_ok"] = None

        self.corrupt_btn.set_state("disabled")
        self.heal_btn.set_state("disabled")
        if self.integrity_monitor:
            self.integrity_monitor.reset()

        if not keep_choice:
            self.original_path = None
            self.output_dir = None
            self.kind = None
            self.state["chosen"] = False
            self.file_label.configure(text="No file selected")
            self.protect_btn.set_state("disabled")
            for key in self.panels:
                self.render_panel(key, None)
        else:
            self.protect_btn.set_state("normal" if self.original_path else "disabled")
            self.render_panel("unprotected", None)
            self.render_panel("healed", None)

        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")
        self.update_status()


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        app = BitRotGuardApp()
        app.mainloop()
