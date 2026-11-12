
import os
import re
import base64
import wave
from pathlib import Path
from google import genai

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

INPUT_FILE = Path("output/script.txt")
OUTPUT_FILE = Path("output/voiceover.wav")

def clean_script(text):
    lines = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        if re.match(
            r"^(visual|b-roll|on-screen|fact-check|fact check|"
            r"editor note|source note|graphics|music|sound effect)\s*:",
            line,
            re.I
        ):
            continue

        if line.startswith("[VISUAL") or line.startswith("[B-ROLL"):
            continue

        if line.startswith("#"):
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

    response = client.interactions.create(
        model="gemini-3.1-flash-tts-preview",
        input=(
            "Say in a mature, deep, authoritative American English "
            "financial documentary narrator voice. "
            "Use calm cinematic storytelling and natural pauses. "
            "Read only the transcript below:\n\n"
            + chunk
        ),
        response_format={"type": "audio"},
        generation_config={
            "speech_config": [
                {"voice": "Gacrux"}
            ]
        }
    )

    if not response.output_audio:
        raise RuntimeError("No audio returned by Gemini")

    audio_parts.append(
        base64.b64decode(response.output_audio.data)
    )

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

with wave.open(str(OUTPUT_FILE), "wb") as wav:
    wav.setnchannels(1)
    wav.setsampwidth(2)
    wav.setframerate(24000)

    for part in audio_parts:
        wav.writeframes(part)

print("SUCCESS: Voiceover created!")
print(OUTPUT_FILE)
