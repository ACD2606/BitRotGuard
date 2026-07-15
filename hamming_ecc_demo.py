#!/usr/bin/env python3
"""
BitRot Guard — Core ECC Demo (standalone)
==========================================
Self-contained showcase of the Hamming(7,4) single-error-correcting code
this project is built on. No Flask, no tkinter, no third-party deps —
just the stdlib. This is the algorithmic heart of BitRot Guard; the web
app (app.py + friends) is a UI wrapped around exactly this logic.

Each 4-bit nibble (d1 d2 d3 d4) is encoded into a 7-bit codeword by adding
3 parity bits at positions 1, 2, 4:
    p1 = d1 ^ d2 ^ d4      (covers positions 1,3,5,7)
    p2 = d1 ^ d3 ^ d4      (covers positions 2,3,6,7)
    p3 = d2 ^ d3 ^ d4      (covers positions 4,5,6,7)

On decode, recomputing those checks yields a 3-bit "syndrome" whose value
IS the 1-indexed position of the flipped bit (0 = no error) — the property
that makes Hamming codes self-locating and lets a single-bit error be
corrected with zero external redundancy checks.

Run:  python hamming_ecc_demo.py [file]
      (no file given -> runs against a small built-in sample)
"""

import hashlib
import random
import struct
import sys

MAGIC = b"BRG1"

# ---------------------------------------------------------------------------
# Hamming(7,4) — build once as lookup tables for speed
# ---------------------------------------------------------------------------


def _build_encode_table():
    table = []
    for nibble in range(16):
        d1, d2, d3, d4 = (nibble >> 3) & 1, (nibble >> 2) & 1, (nibble >> 1) & 1, nibble & 1
        p1, p2, p3 = d1 ^ d2 ^ d4, d1 ^ d3 ^ d4, d2 ^ d3 ^ d4
        codeword = 0
        for b in (p1, p2, d1, p3, d2, d3, d4):
            codeword = (codeword << 1) | b
        table.append(codeword)
    return table


def _build_decode_table():
    table = []
    for codeword in range(128):
        bits = [(codeword >> (6 - i)) & 1 for i in range(7)]
        r1, r2, r3, r4, r5, r6, r7 = bits
        syndrome = (r1 ^ r3 ^ r5 ^ r7) | ((r2 ^ r3 ^ r6 ^ r7) << 1) | ((r4 ^ r5 ^ r6 ^ r7) << 2)
        corrected = bits[:]
        if syndrome:
            corrected[syndrome - 1] ^= 1
        d1, d2, d3, d4 = corrected[2], corrected[4], corrected[5], corrected[6]
        nibble = (d1 << 3) | (d2 << 2) | (d3 << 1) | d4
        table.append((nibble, 1 if syndrome else 0))
    return table


ENCODE_TABLE = _build_encode_table()
DECODE_TABLE = _build_decode_table()


def hamming_encode(data: bytes) -> bytes:
    buf, count, out = 0, 0, bytearray()
    for byte in data:
        for nibble in (byte >> 4, byte & 0xF):
            buf = (buf << 7) | ENCODE_TABLE[nibble]
            count += 7
            while count >= 8:
                count -= 8
                out.append((buf >> count) & 0xFF)
                buf &= (1 << count) - 1
    if count:
        out.append((buf << (8 - count)) & 0xFF)
    return bytes(out)


def hamming_decode(data: bytes, original_size: int):
    num_nibbles = original_size * 2
    buf, count, out = 0, 0, bytearray()
    corrected, done, pending = 0, 0, None
    for byte in data:
        buf, count = (buf << 8) | byte, count + 8
        while count >= 7 and done < num_nibbles:
            count -= 7
            nibble, err = DECODE_TABLE[(buf >> count) & 0x7F]
            buf &= (1 << count) - 1
            corrected += err
            done += 1
            if pending is None:
                pending = nibble
            else:
                out.append((pending << 4) | nibble)
                pending = None
        if done >= num_nibbles:
            break
    return bytes(out), corrected


def flip_random_bits(data: bytes, num_bits: int, seed=None) -> bytes:
    """Simulate bit-rot: flip `num_bits` random bits in a byte string."""
    buf = bytearray(data)
    total_bits = len(buf) * 8
    positions = random.Random(seed).sample(range(total_bits), min(num_bits, total_bits))
    for pos in positions:
        buf[pos // 8] ^= 1 << (7 - pos % 8)
    return bytes(buf)


# ---------------------------------------------------------------------------
# .hprot container: MAGIC | size(8) | sha256(32) | hamming-encoded payload
# ---------------------------------------------------------------------------


def protect(data: bytes) -> bytes:
    digest = hashlib.sha256(data).digest()
    header = MAGIC + struct.pack(">Q", len(data)) + digest
    return header + hamming_encode(data)


def heal(protected: bytes):
    if protected[:4] != MAGIC:
        raise ValueError("not a valid .hprot payload")
    original_size = struct.unpack(">Q", protected[4:12])[0]
    digest = protected[12:44]
    recovered, corrected = hamming_decode(protected[44:], original_size)
    ok = hashlib.sha256(recovered).digest() == digest
    return recovered, corrected, ok


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


HEADER_LEN = 44  # MAGIC(4) + size(8) + sha256(32), never touched by corruption


def run_demo(data: bytes, label: str, num_flips: int = 40, seed: int = 1):
    print(f"\n=== {label} ({len(data)} bytes) ===")

    protected = protect(data)
    overhead = (len(protected) - len(data)) / len(data) * 100
    print(f"Protected:   {len(protected)} bytes  ({overhead:+.1f}% overhead)")

    # Only the encoded payload simulates bit-rot — the header (size/digest)
    # is metadata, not "data on disk" subject to the same rot in this demo.
    header, encoded = protected[:HEADER_LEN], protected[HEADER_LEN:]
    corrupted = header + flip_random_bits(encoded, num_flips, seed=seed)
    print(f"Corrupted:   flipped {num_flips} random bits")

    recovered, corrected, ok = heal(corrupted)
    status = "RECOVERED (SHA-256 match)" if ok else "PARTIAL — 2+ errors in a block"
    print(f"Healed:      corrected {corrected} bit error(s) -> {status}")

    # Contrast: same corruption pattern, no ECC at all
    raw_corrupted = flip_random_bits(data, num_flips, seed=seed)
    raw_ok = raw_corrupted == data
    print(f"No ECC:      same {num_flips} flips on raw bytes -> "
          f"{'somehow intact' if raw_ok else 'permanently corrupted, unrecoverable'}")

    return ok


def _selftest():
    random.seed(0)
    for trial in range(200):
        data = bytes(random.randint(0, 255) for _ in range(random.randint(1, 64)))
        protected = protect(data)
        header, encoded = protected[:HEADER_LEN], protected[HEADER_LEN:]
        corrupted = header + flip_random_bits(encoded, 1, seed=trial)  # 1 flip/trial is always correctable
        recovered, _, ok = heal(corrupted)
        assert ok and recovered == data, f"selftest failed on trial {trial}"
    print("Self-test passed: 200/200 single-bit-error trials recovered correctly.")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
        _selftest()
    elif len(sys.argv) > 1:
        with open(sys.argv[1], "rb") as f:
            run_demo(f.read(), sys.argv[1])
    else:
        sample = b"BitRotGuard: demonstrating Hamming(7,4) self-healing storage. " * 20
        run_demo(sample, "built-in sample")
        print("\nTip: run `python hamming_ecc_demo.py --selftest` or pass a file path.")
