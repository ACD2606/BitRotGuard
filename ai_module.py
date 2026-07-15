"""
AI Module — Gemini-powered intelligence for BitRot Guard
=========================================================
Provides three capabilities:
  1. chat()         — conversational Q&A about bit rot, ECC, Hamming codes
  2. analyze_file() — risk assessment based on file type & size
  3. explain_step() — contextual narration after each workflow step

Gracefully degrades: when no API key is configured or the library isn't
installed, every function returns a high-quality pre-written educational
response so the app remains fully functional offline.
"""

import os
import json

# ---------------------------------------------------------------------------
# Optional Gemini SDK (google-genai — the google-generativeai package this
# used to import is EOL; this is Google's unified replacement SDK)
# ---------------------------------------------------------------------------
try:
    from google import genai
    HAS_GENAI = True
except ImportError:
    HAS_GENAI = False

_api_key = None
_client = None


def configure(api_key: str):
    """Set the Gemini API key and initialise the client."""
    global _api_key, _client
    _api_key = api_key
    if HAS_GENAI and api_key:
        try:
            _client = genai.Client(api_key=api_key)
        except Exception:
            _client = None
    else:
        _client = None


def is_configured() -> bool:
    return _client is not None


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------

MODEL_NAME = "gemini-3.5-flash"

SYSTEM_PROMPT = (
    "You are an expert computer science tutor embedded inside 'BitRot Guard', "
    "an educational tool that demonstrates Hamming(7,4) error-correcting codes. "
    "Your audience is a college student. Explain concepts clearly, use analogies, "
    "and relate answers to the app's workflow (protect → corrupt → heal). "
    "Keep answers concise (3–6 sentences) unless the user asks for detail. "
    "Use markdown formatting for code, formulas, and emphasis. "
    "When discussing math, show the actual parity equations."
)


def _call_gemini(prompt: str, context: str = "") -> str | None:
    """Call Gemini and return the text response, or None on failure."""
    if not _client:
        return None
    try:
        full_prompt = f"{SYSTEM_PROMPT}\n\n"
        if context:
            full_prompt += f"Current app context:\n{context}\n\n"
        full_prompt += f"User question:\n{prompt}"
        response = _client.models.generate_content(model=MODEL_NAME, contents=full_prompt)
        return response.text
    except Exception as e:
        print(f"Gemini API Error: {e}")
        return None


# ---------------------------------------------------------------------------
# 1. Chat
# ---------------------------------------------------------------------------

FALLBACK_RESPONSES = {
    "bit rot": (
        "**Bit rot** (also called *data degradation* or *silent data corruption*) "
        "is the gradual decay of digital data stored on physical media. Over time, "
        "individual bits can spontaneously flip due to:\n\n"
        "- **Cosmic rays** striking memory cells\n"
        "- **Magnetic decay** on hard drives\n"
        "- **Charge leakage** in SSDs and flash storage\n"
        "- **Electrical interference** during read/write\n\n"
        "The scary part? It's *silent* — your operating system won't warn you. "
        "A single flipped bit in a JPEG can corrupt the entire image from that point "
        "onward. ECC (error-correcting codes) like Hamming(7,4) weave mathematical "
        "redundancy into the data so flipped bits can be detected and repaired automatically."
    ),
    "hamming": (
        "**Hamming(7,4)** is an error-correcting code invented by Richard Hamming at "
        "Bell Labs in 1950. Here's how it works:\n\n"
        "1. Take **4 data bits** (d₁ d₂ d₃ d₄)\n"
        "2. Compute **3 parity bits**:\n"
        "   - p₁ = d₁ ⊕ d₂ ⊕ d₄\n"
        "   - p₂ = d₁ ⊕ d₃ ⊕ d₄\n"
        "   - p₃ = d₂ ⊕ d₃ ⊕ d₄\n"
        "3. Arrange as **7-bit codeword**: [p₁ p₂ d₁ p₃ d₂ d₃ d₄]\n\n"
        "The magic: on decoding, recomputing the parity checks gives a 3-bit "
        "**syndrome** whose value *is* the position of the flipped bit (0 = no error). "
        "This self-locating property lets you correct any single-bit error per block "
        "without knowing which bit flipped — the math tells you!"
    ),
    "syndrome": (
        "The **syndrome** is the key to Hamming's error-correction magic. After receiving "
        "a 7-bit codeword, you recompute 3 parity checks:\n\n"
        "- s₁ = r₁ ⊕ r₃ ⊕ r₅ ⊕ r₇\n"
        "- s₂ = r₂ ⊕ r₃ ⊕ r₆ ⊕ r₇\n"
        "- s₃ = r₄ ⊕ r₅ ⊕ r₆ ⊕ r₇\n\n"
        "The resulting 3-bit number (s₃s₂s₁) is the **syndrome**:\n"
        "- Syndrome = 0 → no error\n"
        "- Syndrome = N → bit at position N is flipped; flip it back!\n\n"
        "This works because each parity bit covers a specific pattern of positions "
        "(powers of 2), and the syndrome is essentially a binary address pointing "
        "at the error."
    ),
    "parity": (
        "A **parity bit** is the simplest form of error detection. You count the "
        "number of 1-bits in a group of data bits:\n\n"
        "- **Even parity**: add a bit so the total count of 1s is even\n"
        "- **Odd parity**: add a bit so the total count is odd\n\n"
        "If a single bit flips, the parity check fails → error detected! "
        "But you can't tell *which* bit flipped, so you can't correct it.\n\n"
        "Hamming(7,4) uses **3 overlapping parity groups** covering different "
        "subsets of the 7 positions. The combination of which checks pass/fail "
        "pinpoints the exact error location — turning detection into correction."
    ),
    "ecc": (
        "**ECC (Error-Correcting Code)** is any encoding scheme that adds structured "
        "redundancy so errors can be detected and/or corrected. The hierarchy:\n\n"
        "| Code | Overhead | Detects | Corrects |\n"
        "|------|----------|---------|----------|\n"
        "| Simple Parity | 12.5% | 1-bit errors | None |\n"
        "| Hamming(7,4) | 75% | 1-bit errors | 1-bit errors |\n"
        "| Reed-Solomon | Variable | Burst errors | Burst errors |\n\n"
        "Real-world uses:\n"
        "- **ECC RAM** uses Hamming codes to fix memory bit flips\n"
        "- **QR codes** use Reed-Solomon to survive damage and smudges\n"
        "- **CDs/DVDs** use Reed-Solomon to play despite scratches\n"
        "- **5G/WiFi** use LDPC codes for reliable wireless transmission"
    ),
    "overhead": (
        "**Overhead** is the extra storage cost of adding error correction. "
        "Hamming(7,4) turns every 4 data bits into 7 bits — that's 75% overhead "
        "(your file grows by ~75%).\n\n"
        "Is that a lot? It depends on what you're protecting:\n"
        "- A 1 MB photo becomes ~1.75 MB — totally acceptable for archival\n"
        "- A 1 TB database becoming 1.75 TB — expensive, but cheaper than data loss\n\n"
        "More advanced codes like Reed-Solomon and LDPC achieve much lower overhead "
        "while still providing strong correction. Hamming(7,4) is the *simplest* "
        "code that can actually correct errors — it's the teaching example, not the "
        "industrial solution."
    ),
    "two bit": (
        "Great question! Hamming(7,4) can only **guarantee correction of 1 bit error** "
        "per 7-bit block. If 2 bits flip in the same block:\n\n"
        "- The syndrome will be non-zero (error detected!)\n"
        "- But it will point to the **wrong** position\n"
        "- \"Correcting\" it actually introduces a *third* error\n\n"
        "This is why the app sometimes shows '⚠ hash mismatch' after heavy corruption. "
        "To handle 2-bit errors, you'd need **SECDED** (Single Error Correction, "
        "Double Error Detection) — Hamming(7,4) plus one extra overall parity bit, "
        "giving an 8-bit code that can detect (but not correct) 2-bit errors."
    ),
    "real world": (
        "Error-correcting codes are **everywhere** — you use them daily without knowing:\n\n"
        "🖥️ **ECC RAM**: Server memory uses Hamming codes; a single bit flip in 8 GB "
        "of RAM happens roughly once every few days due to cosmic rays\n\n"
        "📱 **QR Codes**: Reed-Solomon encoding lets your phone scan a QR code even if "
        "30% of it is damaged or covered\n\n"
        "💿 **CDs/DVDs/Blu-ray**: Reed-Solomon survives scratches and fingerprints\n\n"
        "📡 **Deep Space**: NASA's Voyager probes use convolutional codes to send data "
        "across billions of miles with tiny transmitters\n\n"
        "📶 **5G/WiFi**: LDPC and polar codes make wireless reliable despite interference"
    ),
    "help": (
        "Here are things you can ask me about:\n\n"
        "- **\"What is bit rot?\"** — why files silently corrupt over time\n"
        "- **\"How does Hamming(7,4) work?\"** — the encoding and decoding math\n"
        "- **\"What is a syndrome?\"** — how errors are located\n"
        "- **\"What are parity bits?\"** — the building blocks of ECC\n"
        "- **\"What is ECC?\"** — the family of error-correcting codes\n"
        "- **\"Why can't Hamming fix 2-bit errors?\"** — limitations\n"
        "- **\"What's the overhead?\"** — the cost of protection\n"
        "- **\"Real-world examples?\"** — where ECC is used daily\n\n"
        "Or ask me anything else about the demo, error correction, or information theory!"
    ),
}

DEFAULT_FALLBACK = (
    "That's a great question! While I'm running in offline mode right now "
    "(no AI API key configured), here's what I can tell you:\n\n"
    "BitRot Guard demonstrates **Hamming(7,4)** error correction — a code that "
    "adds 3 parity bits to every 4 data bits, creating a 7-bit codeword that can "
    "self-locate and correct any single-bit error.\n\n"
    "Try asking me about: **bit rot**, **Hamming codes**, **syndromes**, "
    "**parity bits**, **ECC**, **overhead**, or **real-world examples**.\n\n"
    "💡 *To enable full AI chat, enter a Google Gemini API key in Settings.*"
)


def _find_fallback(message: str) -> str:
    """Match the user's message to the best pre-written response."""
    msg = message.lower()
    # Score each fallback by keyword matches
    best_key = None
    best_score = 0
    for key in FALLBACK_RESPONSES:
        keywords = key.split()
        score = sum(1 for kw in keywords if kw in msg)
        if score > best_score:
            best_score = score
            best_key = key
    if best_key and best_score > 0:
        return FALLBACK_RESPONSES[best_key]
    # Check for help-like queries
    if any(w in msg for w in ("help", "what can", "how to", "menu", "options")):
        return FALLBACK_RESPONSES["help"]
        
    if _api_key:
        return (
            "I'm currently running in offline educational fallback mode (either because "
            "the Gemini API key hit Google's free-tier rate limit, or the request failed). "
            "Here's what I can tell you:\n\n"
            "BitRot Guard demonstrates **Hamming(7,4)** error correction — a code that "
            "adds 3 parity bits to every 4 data bits, creating a 7-bit codeword that can "
            "self-locate and correct any single-bit error.\n\n"
            "Try asking me about: **bit rot**, **Hamming codes**, **syndromes**, "
            "**parity bits**, **ECC**, **overhead**, or **real-world examples**.\n\n"
            "💡 *The API key should automatically unlock once Google's rate-limit timer resets in a minute.*"
        )
    return DEFAULT_FALLBACK


def chat(message: str, context: str = "") -> dict:
    """Send a chat message and return the response."""
    ai_response = _call_gemini(message, context)
    if ai_response:
        return {"source": "gemini", "message": ai_response}
    return {"source": "fallback", "message": _find_fallback(message)}


# ---------------------------------------------------------------------------
# 2. File Analysis
# ---------------------------------------------------------------------------

FILE_RISK_PROFILES = {
    "text": {
        "risk_level": "Medium",
        "risk_score": 55,
        "analysis": (
            "**Text files** are moderately vulnerable to bit rot. A single bit flip "
            "can turn a letter into a completely different character or an invalid UTF-8 "
            "sequence (displayed as `�`). However, text is human-readable, so corruption "
            "is usually *noticeable* — unlike binary formats where corruption is silent.\n\n"
            "**Real-world risk**: Configuration files, source code, and logs stored on aging "
            "drives can develop subtle typos that cause mysterious bugs months later."
        ),
    },
    "image": {
        "risk_level": "High",
        "risk_score": 78,
        "analysis": (
            "**Image files** are highly vulnerable to bit rot, especially compressed "
            "formats like JPEG. A single bit flip in a JPEG's Huffman table or quantization "
            "matrix can **cascade** — corrupting everything from that point to the end of "
            "the image (the classic 'gray band' corruption).\n\n"
            "PNG files use per-row CRC checks, so corruption tends to produce localized "
            "color artifacts rather than total destruction.\n\n"
            "**Real-world risk**: Family photos, medical imaging archives, and satellite "
            "imagery are prime candidates for ECC protection."
        ),
    },
    "binary": {
        "risk_level": "Critical",
        "risk_score": 90,
        "analysis": (
            "**Binary files** (executables, databases, archives) are *extremely* vulnerable. "
            "A single bit flip can:\n\n"
            "- **Executables**: Crash the program, trigger security vulnerabilities, or cause "
            "silent miscalculation\n"
            "- **Databases**: Corrupt records, break indices, cause cascading query failures\n"
            "- **Archives (ZIP/tar)**: Make the entire archive unextractable\n\n"
            "**Real-world risk**: Financial systems, scientific datasets, and backup archives "
            "are where bit rot does the most damage — and it's almost always undetected "
            "until someone tries to use the data months or years later."
        ),
    },
}


def analyze_file(filename: str, file_size: int, file_kind: str) -> dict:
    """Generate a risk analysis for the selected file."""
    profile = FILE_RISK_PROFILES.get(file_kind, FILE_RISK_PROFILES["binary"])

    # Try Gemini for a richer analysis
    if _client:
        prompt = (
            f"The user selected a file for bit-rot protection:\n"
            f"- Filename: {filename}\n"
            f"- Size: {file_size:,} bytes\n"
            f"- Type: {file_kind}\n\n"
            f"Give a brief (4-6 sentences) risk analysis: how vulnerable is this "
            f"file type to bit rot? What real-world scenarios could cause problems? "
            f"Rate the risk as Low/Medium/High/Critical with a score out of 100."
        )
        ai_text = _call_gemini(prompt)
        if ai_text and not ai_text.startswith("⚠️"):
            return {
                "source": "gemini",
                "risk_level": profile["risk_level"],
                "risk_score": profile["risk_score"],
                "analysis": ai_text,
            }

    return {
        "source": "fallback",
        "risk_level": profile["risk_level"],
        "risk_score": profile["risk_score"],
        "analysis": profile["analysis"],
    }


# ---------------------------------------------------------------------------
# 3. Step Explanation
# ---------------------------------------------------------------------------

STEP_EXPLANATIONS = {
    "protect": (
        "### 🛡️ Protection Complete\n\n"
        "Your file has been encoded with **Hamming(7,4)** error correction. "
        "Here's what just happened:\n\n"
        "1. The file was split into **4-bit nibbles** (two per byte)\n"
        "2. Each nibble received **3 parity bits**, creating a 7-bit codeword\n"
        "3. All codewords were packed into a `.hprot` file along with:\n"
        "   - The original filename\n"
        "   - The original file size\n"
        "   - A SHA-256 hash for verification\n\n"
        "The protected file is ~75% larger than the original — that's the cost of "
        "redundancy. But that redundancy is what will let us recover from bit rot.\n\n"
        "A plain unprotected copy was also saved for comparison — same data, zero "
        "protection. Both copies will be subjected to the same number of random bit flips."
    ),
    "corrupt": (
        "### 💥 Bit Rot Simulated\n\n"
        "Random bits have been flipped in **both** copies — the protected `.hprot` file "
        "and the unprotected plain copy. This simulates what happens to real files over time "
        "on aging storage media.\n\n"
        "**Key insight**: Real bit rot gives you *no warning*. Your file looks normal "
        "in the file manager, the size hasn't changed, and the OS reports no errors. "
        "But the data inside has been silently mutated.\n\n"
        "The unprotected copy is now permanently damaged — those flipped bits are lost "
        "forever. The protected copy's bits are also flipped, but the Hamming redundancy "
        "is still intact, waiting to be decoded.\n\n"
        "Click **Heal** to see the magic of error correction!"
    ),
    "heal": (
        "### ✨ Healing Complete\n\n"
        "The protected file has been decoded through Hamming(7,4) error correction:\n\n"
        "1. Each 7-bit codeword was extracted from the `.hprot` file\n"
        "2. Three parity checks were recomputed, producing a **syndrome**\n"
        "3. Non-zero syndromes identified exactly which bit was flipped\n"
        "4. Those bits were flipped back to their original values\n"
        "5. The 4 data bits were extracted from each corrected codeword\n"
        "6. The recovered file was verified against the stored SHA-256 hash\n\n"
        "**Result**: The healed file is *byte-for-byte identical* to the original. "
        "Meanwhile, the unprotected copy remains permanently corrupted.\n\n"
        "This is why ECC matters — mathematical redundancy beats physical decay."
    ),
    "heal_failed": (
        "### ⚠️ Partial Recovery\n\n"
        "The healed file does **not** match the original SHA-256 hash. This means "
        "some 7-bit blocks suffered **2 or more** simultaneous bit flips — beyond "
        "what Hamming(7,4) can correct.\n\n"
        "**Why?** Hamming(7,4) is a *Single Error Correcting* (SEC) code. If two "
        "bits flip in the same 7-bit block, the syndrome points to the wrong position, "
        "and 'correcting' it makes things worse.\n\n"
        "**Solutions** for stronger protection:\n"
        "- **SECDED**: Add 1 more parity bit → detect (not correct) 2-bit errors\n"
        "- **Reed-Solomon**: Correct burst errors across multiple bytes\n"
        "- **LDPC**: Near-Shannon-limit performance used in 5G and SSDs\n\n"
        "Try again with fewer bit flips to see Hamming(7,4) succeed!"
    ),
}


def explain_step(step: str, context: dict = None) -> dict:
    """Generate an educational explanation for a workflow step."""
    ctx = context or {}

    if _client:
        ctx_str = json.dumps(ctx, default=str)
        prompt = (
            f"The user just completed the '{step}' step in the BitRot Guard demo.\n"
            f"Context: {ctx_str}\n\n"
            f"Give a clear, educational explanation (5-8 sentences with markdown) of "
            f"what just happened mathematically and why it matters. Be enthusiastic "
            f"but precise. Include relevant numbers from the context."
        )
        ai_text = _call_gemini(prompt)
        if ai_text and not ai_text.startswith("⚠️"):
            return {"source": "gemini", "explanation": ai_text}

    fallback_key = step
    if step == "heal" and ctx.get("hash_ok") is False:
        fallback_key = "heal_failed"

    explanation = STEP_EXPLANATIONS.get(fallback_key, STEP_EXPLANATIONS.get("protect"))
    return {"source": "fallback", "explanation": explanation}
