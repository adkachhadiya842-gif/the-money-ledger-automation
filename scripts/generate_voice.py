
import os
import re
import json
import base64
import wave
import struct
import time
import urllib.request
import urllib.error
from pathlib import Path

# API key from GitHub Secrets
API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY missing in GitHub Secrets!")

MODEL = "gemini-2.5-flash-preview-tts"
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
        line = re.sub(
            r"^\*\*NARRATOR:\*\*\s*", "", line, flags=re.I
        )
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
                    "Read the following text in a mature, deep, "
                    "authoritative American English financial "
                    "documentary narration style. Speak calmly, "
                    "clearly, and naturally with suitable pauses. "
                    "Read only the supplied narration:\n\n"
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
            f"Gemini TTS API error {error.code}: {details}"
        )

    print("DEBUG: Response keys:", list(result.keys()))

    for candidate in result.get("candidates", []):
        print("DEBUG: Finish reason:", candidate.get("finishReason"))

        for part in candidate.get("content", {}).get("parts", []):
            print("DEBUG: Part keys:", list(part.keys()))

            inline = part.get("inlineData") or part.get("inline_data")

            if inline and inline.get("data"):
                audio_data = base64.b64decode(inline["data"])
                mime_type = inline.get("mimeType", "")
                print("Audio MIME:", mime_type)
                return audio_data, mime_type

    print("DEBUG: Prompt feedback:", result.get("promptFeedback"))
    raise RuntimeError(
        "Gemini returned no audio data. Check model access and API response."
    )


def pcm_to_wav(audio_parts, mime_types):
    combined = b"".join(audio_parts)

    # Gemini TTS normally returns raw PCM audio.
    # Default output format: 24 kHz, mono, 16-bit PCM.
    sample_rate = 24000
    channels = 1
    sample_width = 2

    for mime in mime_types:
        match = re.search(r"rate=(\d+)", mime or "")
        if match:
            sample_rate = int(match.group(1))
            break

    # Remove incomplete final PCM sample if necessary.
    combined = combined[:len(combined) - (len(combined) % 2)]

    if not combined:
        raise ValueError("No valid PCM audio received!")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(OUTPUT_FILE), "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(sample_width)
        wav.setframerate(sample_rate)
        wav.writeframes(combined)


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError("output/script.txt not found!")

    script = clean_script(
        INPUT_FILE.read_text(encoding="utf-8")
    )

    if not script:
        raise ValueError("No narration text found!")

    chunks = make_chunks(script)

    print("Total narration chunks:", len(chunks))

    audio_parts = []
    mime_types = []

    for index, chunk in enumerate(chunks, 1):
        print(f"Generating voice {index}/{len(chunks)}")

        for attempt in range(1, 4):
            try:
                audio_data, mime_type = generate_audio(chunk)
                audio_parts.append(audio_data)
                mime_types.append(mime_type)
                break

            except Exception as error:
                print(f"Attempt {attempt} failed:", error)

                if attempt == 3:
                    raise

                time.sleep(attempt * 5)

    pcm_to_wav(audio_parts, mime_types)

    print("SUCCESS: Voiceover created!")
    print("Output:", OUTPUT_FILE)


if __name__ == "__main__":
    main()
