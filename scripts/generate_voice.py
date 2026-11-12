
import os
import re
import wave
import base64
from pathlib import Path
from google import genai

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY secret is missing")

client = genai.Client(api_key=API_KEY)

INPUT_FILE = Path("output/script.txt")
OUTPUT_FILE = Path("output/voiceover.wav")

def clean_script(text):
    lines = []

    for line in text.splitlines():
        stripped = line.strip()

        if not stripped:
            lines.append("")
            continue

        # Remove visual and production directions
        if re.match(
            r"^(visual|b-roll|on-screen|fact-check|fact check|"
            r"editor note|source note|graphics|music|sound effect)\s*:",
            stripped,
            re.IGNORECASE
        ):
            continue

        if stripped.startswith("[VISUAL") or stripped.startswith("[B-ROLL"):
            continue

        if stripped.startswith("##"):
            continue

        stripped = re.sub(r"^\*\*NARRATOR:\*\*\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"^NARRATOR:\s*", "", stripped, flags=re.I)
        stripped = re.sub(r"\*\*(.*?)\*\*", r"\1", stripped)

        lines.append(stripped)

    return "\n".join(lines).strip()

def make_chunks(text, limit=2500):
    paragraphs = text.split("\n")
    chunks = []
    current = ""

    for paragraph in paragraphs:
        if len(current) + len(paragraph) > limit and current:
            chunks.append(current.strip())
            current = ""

        current += paragraph + "\n"

    if current.strip():
        chunks.append(current.strip())

    return chunks

if not INPUT_FILE.exists():
    raise FileNotFoundError("output/script.txt not found")

script = clean_script(INPUT_FILE.read_text(encoding="utf-8"))

if not script:
    raise ValueError("No narration text found in script")

chunks = make_chunks(script)
audio_parts = []

for index, chunk in enumerate(chunks, start=1):
    print(f"Generating voice part {index}/{len(chunks)}")

    response = client.interactions.create(
        model="gemini-3.8-flash-tts",
        input=(
            "Read this as a premium American financial documentary narrator. "
            "Use a mature, deep, calm, authoritative American English voice. "
            "Cinematic storytelling, natural pauses, clear pronunciation. "
            "Do not sound like an advertisement.\n\n"
            + chunk
        ),
        response_format={"type": "audio"},
        generation_config={
            "speech_config": [
                {"voice": "Charon"}
            ]
        }
    )

    audio = base64.b64decode(response.output_audio.data)
    audio_parts.append(audio)

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

with wave.open(str(OUTPUT_FILE), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(24000)

    for part in audio_parts:
        wav.writeframes(part)

print(f"Voiceover created: {OUTPUT_FILE}")
