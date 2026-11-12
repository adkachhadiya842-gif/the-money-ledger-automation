
import os
import re
import base64
import wave
from io import BytesIO
from pathlib import Path
from google import genai

client = genai.Client(
    api_key=os.environ["GEMINI_API_KEY"]
)

INPUT_FILE = Path("output/script.txt")
OUTPUT_FILE = Path("output/voiceover.wav")

def clean_script(text):
    result = []

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

        result.append(line)

    return "\n".join(result)

def make_chunks(text, limit=2500):
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
audio_frames = []

for i, chunk in enumerate(chunks, 1):
    print(f"Generating voice {i}/{len(chunks)}")

    response = client.interactions.create(
        model="gemini-3.8-flash-tts",
        input=[{
            "type": "user_input",
            "content": [{
                "type": "text",
                "text": chunk,
                "annotations": [{
                    "type": "speech_metadata",
                    "style": (
                        "Mature, deep, authoritative American "
                        "financial documentary narrator. "
                        "Calm cinematic storytelling with "
                        "natural pauses and clear pronunciation."
                    )
                }]
            }]
        }],
        response_format={"type": "audio"},
        generation_config={
            "speech_config": [
                {"voice": "Gacrux"}
            ]
        }
    )

    wav_bytes = base64.b64decode(
        response.output_audio.data
    )

    with wave.open(BytesIO(wav_bytes), "rb") as wav:
        if wav.getnchannels() != 1 or wav.getframerate() != 24000:
            raise ValueError("Unexpected audio format")

        audio_frames.append(wav.readframes(wav.getnframes()))

OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

with wave.open(str(OUTPUT_FILE), "wb") as output:
    output.setnchannels(1)
    output.setsampwidth(2)
    output.setframerate(24000)

    for frames in audio_frames:
        output.writeframes(frames)

print("SUCCESS: Voiceover created!")
print(OUTPUT_FILE)
