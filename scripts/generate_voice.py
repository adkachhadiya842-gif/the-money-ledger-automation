
import os
import re
import json
import base64
import wave
import urllib.request
import urllib.error
from pathlib import Path

API_KEY = os.environ["GEMINI_API_KEY"]

MODEL = "gemini-3.1-flash-tts-preview"
VOICE = "Gacrux"

INPUT_FILE = Path("output/script.txt")
OUTPUT_FILE = Path("output/voiceover.wav")


def clean_script(text):
    lines = []

    for line in text.splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        if re.match(
            r"^(visual|b-roll|on-screen|fact-check|"
            r"fact check|editor note|source note|graphics|"
            r"music|sound effect)\s*:",
            line,
            re.I
        ):
            continue

        if line.startswith("[VISUAL") or line.startswith("[B-ROLL"):
            continue

        line = re.sub(r"\*\*(.*?)\*\*", r"\1", line)
        line = re.sub(r"^\*\*NARRATOR:\*\*\s*", "", line, flags=re.I)
        line = re.sub(r"^NARRATOR:\s*", "", line, flags=re.I)

        lines.append(line)

    return "\n".join(lines)


def make_chunks(text, limit=2000):
    sentences = re.split(r'(?<=[.!?])\s+', text)
    chunks = []
    current = ""

    for sentence in sentences:
        if len(current) + len(sentence) > limit and current:
            chunks.append(current.strip())
            current = ""

        current += sentence + " "

    if current.strip():
        chunks.append(current.strip())

    return chunks


def generate_audio(chunk):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{MODEL}:generateContent"
    )

    payload = {
        "contents": [{
            "parts": [{
                "text": (
                    "Say in a mature, deep, authoritative "
                    "American English financial documentary "
                    "narrator voice. Use calm cinematic storytelling "
                    "and natural pauses. Read only this transcript:\n\n"
                    + chunk
                )
            }]
        }],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": VOICE
                    }
                }
            }
        }
    }

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": API_KEY
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))

    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Google TTS API error {error.code}: {details}"
        )

    for candidate in result.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData")

            if inline and inline.get("data"):
                return base64.b64decode(inline["data"])

    raise RuntimeError("Google API returned no audio data")


if not INPUT_FILE.exists():
    raise FileNotFoundError("output/script.txt not found")

script = clean_script(
    INPUT_FILE.read_text(encoding="utf-8")
)

if not script:
    raise ValueError("No narration text found")

chunks = make_chunks(script)
audio_parts = []

for i, chunk in enumerate(chunks, 1):
    print(f"Generating voice {i}/{len(chunks)}")
    audio_parts.append(generate_audio(chunk))

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

with wave.open(str(OUTPUT_FILE), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(24000)

    for part in audio_parts:
        wav.writeframes(part)

print("SUCCESS: Voiceover created!")
print(OUTPUT_FILE)
