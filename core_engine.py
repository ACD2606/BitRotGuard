"""
Core Engine — Hamming(7,4) ECC + .hprot file format
=====================================================
This is the same logic as bitrot_guard.py's core (lines shared 1:1 in
spirit), extracted into its own module so the web backend never imports
tkinter. bitrot_guard.py stays as the original tkinter desktop app for
local use; this module is what app.py and ecc_engines.py import from
when running as a server (Render, or anywhere headless).
"""

import os
import struct
import random
import hashlib

MAGIC = b"BRG1"

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
# flipped bit (0 = no error) — self-locating, corrects any single-bit error
# per 7-bit block.
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


def detect_kind(path):
    """Sniff text / image / binary. PIL-only — no tkinter fallback needed server-side."""
    try:
        with open(path, "rb") as f:
            head = f.read(4096)
        head.decode("utf-8")
        return "text"
    except UnicodeDecodeError:
        pass
    try:
        from PIL import Image
        with Image.open(path) as im:
            im.verify()
        return "image"
    except Exception:
        return "binary"
