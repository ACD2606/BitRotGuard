"""
ECC Comparison Engines
======================
Three error-correction strategies with a common interface, used by the
Compare ECC mode to show the tradeoff between overhead and protection.

1. NoProtection  — raw bytes, zero overhead, zero correction
2. ParityCode    — 1 parity bit per byte (12.5% overhead), detects but can't correct
3. HammingCode   — Hamming(7,4) (75% overhead), corrects any single-bit error per block
"""

import hashlib
import random

# Import the existing Hamming logic (tkinter-free core, safe on a server)
from core_engine import hamming_encode_bytes, hamming_decode_bytes


# ---------------------------------------------------------------------------
# Common base
# ---------------------------------------------------------------------------

class ECCResult:
    """Holds the outcome of an encode → corrupt → decode cycle."""
    __slots__ = (
        "name", "overhead_pct", "encoded_size", "original_size",
        "num_flips", "errors_detected", "errors_corrected",
        "data_recovered", "hash_ok", "description",
    )

    def __init__(self, name):
        self.name = name
        self.overhead_pct = 0.0
        self.encoded_size = 0
        self.original_size = 0
        self.num_flips = 0
        self.errors_detected = 0
        self.errors_corrected = 0
        self.data_recovered = b""
        self.hash_ok = False
        self.description = ""

    def to_dict(self):
        return {
            "name": self.name,
            "overhead_pct": round(self.overhead_pct, 2),
            "encoded_size": self.encoded_size,
            "original_size": self.original_size,
            "num_flips": self.num_flips,
            "errors_detected": self.errors_detected,
            "errors_corrected": self.errors_corrected,
            "hash_ok": self.hash_ok,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# 1. No Protection
# ---------------------------------------------------------------------------

class NoProtection:
    name = "No Protection"
    description = "Raw bytes with zero redundancy — any bit flip permanently corrupts the data."

    @staticmethod
    def run(data: bytes, num_flips: int, seed: int = 42) -> ECCResult:
        r = ECCResult(NoProtection.name)
        r.original_size = len(data)
        r.encoded_size = len(data)
        r.overhead_pct = 0.0
        r.num_flips = num_flips

        original_hash = hashlib.sha256(data).digest()

        # Corrupt
        buf = bytearray(data)
        rng = random.Random(seed)
        total_bits = len(buf) * 8
        flip_count = min(num_flips, total_bits)
        positions = rng.sample(range(total_bits), flip_count)
        for bitpos in positions:
            byte_idx = bitpos // 8
            bit_idx = bitpos % 8
            buf[byte_idx] ^= (1 << (7 - bit_idx))

        # "Decode" — there's nothing to decode, what you see is what you get
        r.data_recovered = bytes(buf)
        r.errors_detected = 0
        r.errors_corrected = 0
        r.hash_ok = hashlib.sha256(r.data_recovered).digest() == original_hash
        r.description = (
            f"No error correction applied. {num_flips} bit(s) flipped → "
            f"data is {'intact' if r.hash_ok else 'permanently corrupted'}. "
            f"Zero overhead, zero protection."
        )
        return r


# ---------------------------------------------------------------------------
# 2. Simple Parity (detection only)
# ---------------------------------------------------------------------------

class ParityCode:
    name = "Simple Parity"
    description = (
        "Adds 1 even-parity bit per byte (12.5% overhead). "
        "Can detect a single-bit error per byte but cannot correct it."
    )

    @staticmethod
    def _encode(data: bytes) -> bytearray:
        """Each byte becomes 9 bits: the original 8 + 1 parity bit.
        We pack these 9-bit units into a byte stream."""
        out = bytearray()
        bit_buf = 0
        bit_count = 0
        for byte in data:
            parity = bin(byte).count("1") & 1  # even parity
            word = (byte << 1) | parity  # 9 bits
            bit_buf = (bit_buf << 9) | word
            bit_count += 9
            while bit_count >= 8:
                bit_count -= 8
                out.append((bit_buf >> bit_count) & 0xFF)
                bit_buf &= (1 << bit_count) - 1
        if bit_count > 0:
            out.append((bit_buf << (8 - bit_count)) & 0xFF)
        return out

    @staticmethod
    def _decode(encoded: bytearray, original_size: int):
        """Extract 9-bit units, check parity, return data + error count."""
        bit_buf = 0
        bit_count = 0
        out = bytearray()
        errors_detected = 0
        units_done = 0
        for byte in encoded:
            bit_buf = (bit_buf << 8) | byte
            bit_count += 8
            while bit_count >= 9 and units_done < original_size:
                bit_count -= 9
                word = (bit_buf >> bit_count) & 0x1FF
                bit_buf &= (1 << bit_count) - 1
                data_byte = (word >> 1) & 0xFF
                parity_bit = word & 1
                expected = bin(data_byte).count("1") & 1
                if parity_bit != expected:
                    errors_detected += 1
                out.append(data_byte)
                units_done += 1
        return bytes(out), errors_detected

    @staticmethod
    def run(data: bytes, num_flips: int, seed: int = 42) -> ECCResult:
        r = ECCResult(ParityCode.name)
        r.original_size = len(data)
        original_hash = hashlib.sha256(data).digest()

        encoded = ParityCode._encode(data)
        r.encoded_size = len(encoded)
        r.overhead_pct = (len(encoded) / len(data) - 1) * 100 if data else 0

        # Corrupt
        rng = random.Random(seed)
        total_bits = len(encoded) * 8
        flip_count = min(num_flips, total_bits)
        positions = rng.sample(range(total_bits), flip_count)
        for bitpos in positions:
            byte_idx = bitpos // 8
            bit_idx = bitpos % 8
            encoded[byte_idx] ^= (1 << (7 - bit_idx))

        recovered, detected = ParityCode._decode(encoded, len(data))
        r.data_recovered = recovered
        r.errors_detected = detected
        r.errors_corrected = 0  # parity can't correct
        r.num_flips = num_flips
        r.hash_ok = hashlib.sha256(r.data_recovered).digest() == original_hash
        r.description = (
            f"Parity detected {detected} byte(s) with errors out of {num_flips} "
            f"bit flip(s), but cannot correct any of them. "
            f"Overhead: {r.overhead_pct:.1f}%. "
            f"Data {'intact' if r.hash_ok else 'corrupted — detection only, no repair'}."
        )
        return r


# ---------------------------------------------------------------------------
# 3. Hamming(7,4)
# ---------------------------------------------------------------------------

class HammingCode:
    name = "Hamming(7,4)"
    description = (
        "Encodes each 4-bit nibble into a 7-bit codeword (75% overhead). "
        "Corrects any single-bit error per 7-bit block — the gold standard "
        "for single-error-correcting codes."
    )

    @staticmethod
    def run(data: bytes, num_flips: int, seed: int = 42) -> ECCResult:
        r = ECCResult(HammingCode.name)
        r.original_size = len(data)
        original_hash = hashlib.sha256(data).digest()

        encoded = bytearray(hamming_encode_bytes(data))
        r.encoded_size = len(encoded)
        r.overhead_pct = (len(encoded) / len(data) - 1) * 100 if data else 0

        # Corrupt
        rng = random.Random(seed)
        total_bits = len(encoded) * 8
        flip_count = min(num_flips, total_bits)
        positions = rng.sample(range(total_bits), flip_count)
        for bitpos in positions:
            byte_idx = bitpos // 8
            bit_idx = bitpos % 8
            encoded[byte_idx] ^= (1 << (7 - bit_idx))

        recovered, corrected = hamming_decode_bytes(bytes(encoded), len(data))
        r.data_recovered = recovered
        r.errors_corrected = corrected
        r.errors_detected = corrected  # Hamming detects what it corrects
        r.num_flips = num_flips
        r.hash_ok = hashlib.sha256(r.data_recovered).digest() == original_hash
        r.description = (
            f"Hamming(7,4) corrected {corrected} error(s) from {num_flips} "
            f"bit flip(s). Overhead: {r.overhead_pct:.1f}%. "
            f"Data {'fully recovered — SHA-256 match!' if r.hash_ok else 'partially recovered — some blocks had 2+ errors'}."
        )
        return r


# ---------------------------------------------------------------------------
# Convenience: run all three and return comparison
# ---------------------------------------------------------------------------

ALL_ENGINES = [NoProtection, ParityCode, HammingCode]


def compare_all(data: bytes, num_flips: int, seed: int = 42):
    """Run all ECC strategies on the same data with the same flip count.
    Returns a list of ECCResult dicts."""
    return [engine.run(data, num_flips, seed).to_dict() for engine in ALL_ENGINES]
