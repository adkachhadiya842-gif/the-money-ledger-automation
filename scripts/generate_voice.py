
import os
import re
import json
import base64
import wave
import time
import urllib.request
import urllib.error
from pathlib import Path
from hashlib import sha256

API_KEY = os.environ.get("GEMINI_API_KEY")

if not API_KEY:
    raise ValueError("GEMINI_API_KEY missing in GitHub Secrets!")

MODEL = "gemini-2.5-flash-preview-tts"
VOICE = "Gacrux"

INPUT_FILE = Path("output/script.txt")
OUTPUT_FILE = Path("output/voiceover.wav")
CHUNKS_DIR = Path("output/tts_chunks")
MANIFEST_FILE = CHUNKS_DIR / "manifest.json"


class QuotaExceededError(RuntimeError):
    pass


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

        if error.code == 429:
            raise QuotaExceededError(
                "Gemini daily quota/rate limit reached. "
                "Completed chunks have been saved. "
                "Wait for quota reset before rerunning."
            )

        raise RuntimeError(
            f"Gemini TTS API error {error.code}: {details}"
        )

    for candidate in result.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")

            if inline and inline.get("data"):
                audio_data = base64.b64decode(inline["data"])
                mime_type = (
                    inline.get("mimeType")
                    or inline.get("mime_type")
                    or ""
                )
                return audio_data, mime_type

    raise RuntimeError("Gemini returned no audio data.")


def save_manifest(data):
    temp = MANIFEST_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    temp.replace(MANIFEST_FILE)


def pcm_to_wav(audio_parts, mime_types):
    combined = b"".join(audio_parts)

    sample_rate = 24000

    for mime in mime_types:
        match = re.search(r"rate=(\d+)", mime or "")
        if match:
            sample_rate = int(match.group(1))
            break

    combined = combined[:len(combined) - (len(combined) % 2)]

    if not combined:
        raise ValueError("No valid PCM audio received!")

    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(OUTPUT_FILE), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(combined)


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError("output/script.txt not found!")

    script = clean_script(INPUT_FILE.read_text(encoding="utf-8"))

    if not script:
        raise ValueError("No narration text found!")

    chunks = make_chunks(script)
    script_hash = sha256(script.encode("utf-8")).hexdigest()

    CHUNKS_DIR.mkdir(parents=True, exist_ok=True)

    if MANIFEST_FILE.exists():
        manifest = json.loads(
            MANIFEST_FILE.read_text(encoding="utf-8")
        )
    else:
        manifest = {}

    # Reset checkpoints if the narration script has changed.
    if (
        manifest.get("script_hash") != script_hash
        or manifest.get("total_chunks") != len(chunks)
    ):
        print("New script detected. Starting fresh checkpoints.")

        for file in CHUNKS_DIR.glob("chunk_*.pcm"):
            file.unlink()

        manifest = {
            "script_hash": script_hash,
            "total_chunks": len(chunks),
            "completed": {}
        }

        save_manifest(manifest)

    print("Total narration chunks:", len(chunks))

    for index, chunk in enumerate(chunks, 1):
        chunk_key = str(index)
        chunk_file = CHUNKS_DIR / f"chunk_{index:03d}.pcm"

        if (
            chunk_key in manifest["completed"]
            and chunk_file.exists()
        ):
            print(f"Skipping completed chunk {index}/{len(chunks)}")
            continue

        print(f"Generating voice {index}/{len(chunks)}")

        for attempt in range(1, 4):
            try:
                audio_data, mime_type = generate_audio(chunk)

                # Save audio immediately after successful generation.
                temp_file = chunk_file.with_suffix(".tmp")
                temp_file.write_bytes(audio_data)
                temp_file.replace(chunk_file)

                manifest["completed"][chunk_key] = mime_type
                save_manifest(manifest)

                print(f"Saved chunk {index}")
                break

            except QuotaExceededError:
                print("Quota reached. Stopping without retry.")
                raise

            except Exception as error:
                print(f"Attempt {attempt} failed: {error}")

                if attempt == 3:
                    raise

                time.sleep(attempt * 5)

    # Join all saved chunks in the correct order.
    audio_parts = []
    mime_types = []

    for index in range(1, len(chunks) + 1):
        chunk_key = str(index)
        chunk_file = CHUNKS_DIR / f"chunk_{index:03d}.pcm"

        if not chunk_file.exists():
            raise RuntimeError(f"Missing audio chunk: {index}")

        audio_parts.append(chunk_file.read_bytes())
        mime_types.append(manifest["completed"].get(chunk_key, ""))

    pcm_to_wav(audio_parts, mime_types)

    print("SUCCESS: Voiceover created!")
    print("Output:", OUTPUT_FILE)

    Path("output/tts_complete.txt").write_text("completed", encoding="utf-8")

if __name__ == "__main__":
    main()
