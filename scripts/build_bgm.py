
import re
import subprocess
import random
from pathlib import Path

# Project paths
ROOT = Path(__file__).resolve().parent.parent
SCRIPT_FILE = ROOT / "output" / "script.txt"
VOICE_FILE = ROOT / "output" / "voiceover.wav"
MUSIC_DIR = ROOT / "music"
TEMP_DIR = ROOT / "output" / "bgm_segments"

BGM_FILE = ROOT / "output" / "background_music.wav"
FINAL_FILE = ROOT / "output" / "final_audio.wav"

# Background music volume.
# Keep it low so narration stays clear.
BGM_VOLUME = 0.12

# Fade duration in seconds
FADE_SECONDS = 1.5

MOOD_KEYWORDS = {
    "mystery": [
        "secret", "hidden", "mystery", "unknown", "shadow",
        "behind the scenes", "silently", "secretly"
    ],
    "suspense": [
        "warning", "danger", "risk", "threat", "investigation",
        "question", "uncertain", "collapse", "unexpected"
    ],
    "crisis": [
        "crisis", "crash", "bankruptcy", "debt", "recession",
        "failure", "panic", "loss", "fraud", "scandal",
        "collapse", "disaster"
    ],
    "growth": [
        "growth", "success", "profit", "innovation", "future",
        "opportunity", "wealth", "rise", "recovery", "expansion"
    ],
    "revelation": [
        "revealed", "discovered", "truth", "reveal", "surprising",
        "what happened", "the reality", "the truth"
    ]
}


def run_command(command):
    """Run FFmpeg and show useful errors."""
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg failed:\n" + result.stderr[-4000:]
        )


def read_script():
    if not SCRIPT_FILE.exists():
        raise FileNotFoundError(f"Script not found: {SCRIPT_FILE}")

    text = SCRIPT_FILE.read_text(encoding="utf-8")

    # Remove fact-check notes and everything after them
    text = re.split(
        r"FACT[- ]CHECK NOTES",
        text,
        flags=re.IGNORECASE
    )[0]

    # Remove common non-narration labels
    text = re.sub(
        r"(?im)^\s*(TITLE|VISUAL|B-ROLL|ON-SCREEN|"
        r"EDITOR NOTE|SOURCE NOTE|GRAPHICS|MUSIC)\s*:.*$",
        "",
        text
    )

    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)

    paragraphs = [
        p.strip()
        for p in re.split(r"\n\s*\n", text)
        if p.strip()
    ]

    # Remove a short opening title line if present
    if paragraphs and len(paragraphs[0].split()) < 12:
        paragraphs = paragraphs[1:]

    if not paragraphs:
        raise ValueError("No narration paragraphs found!")

    return paragraphs


def detect_mood(paragraph):
    text = paragraph.lower()
    scores = {}

    for mood, keywords in MOOD_KEYWORDS.items():
        scores[mood] = sum(
            text.count(keyword)
            for keyword in keywords
        )

    best_mood = max(scores, key=scores.get)

    if scores[best_mood] == 0:
        return "neutral"

    return best_mood


def make_scenes(paragraphs):
    """Combine adjacent paragraphs with the same mood."""
    scenes = []

    for paragraph in paragraphs:
        mood = detect_mood(paragraph)

        if scenes and scenes[-1]["mood"] == mood:
            scenes[-1]["text"] += "\n\n" + paragraph
            scenes[-1]["words"] += len(paragraph.split())
        else:
            scenes.append({
                "mood": mood,
                "text": paragraph,
                "words": len(paragraph.split())
            })

    return scenes


def get_audio_duration():
    """Read narration duration using FFprobe."""
    command = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(VOICE_FILE)
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True
    )

    return float(result.stdout.strip())


def find_music(mood):
    folder = MUSIC_DIR / mood

    files = []
    if folder.exists():
        files = [
            p for p in folder.iterdir()
            if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")
        ]

    if not files and mood != "neutral":
        return find_music("neutral")

    if not files:
        raise FileNotFoundError(
            f"No music files found in {folder}. "
            "Upload at least one licensed music track."
        )

    return random.choice(files)


def create_music_segment(track, output, duration):
    if duration <= 0:
        raise ValueError("Invalid music segment duration")

    fade = min(FADE_SECONDS, duration / 3)

    fade_out_start = max(0, duration - fade)

    audio_filter = (
        f"volume={BGM_VOLUME},"
        f"afade=t=in:st=0:d={fade},"
        f"afade=t=out:st={fade_out_start}:d={fade}"
    )

    command = [
        "ffmpeg", "-y",
        "-stream_loop", "-1",
        "-i", str(track),
        "-t", f"{duration:.3f}",
        "-af", audio_filter,
        "-ar", "44100",
        "-ac", "2",
        "-c:a", "pcm_s16le",
        str(output)
    ]

    run_command(command)


def join_segments(segment_files):
    concat_file = TEMP_DIR / "concat.txt"

    with concat_file.open("w", encoding="utf-8") as file:
        for segment in segment_files:
            safe_path = segment.resolve().as_posix().replace("'", "'\\''")
            file.write(f"file '{safe_path}'\n")

    command = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-c:a", "pcm_s16le",
        str(BGM_FILE)
    ]

    run_command(command)


def mix_voice_and_music():
    command = [
        "ffmpeg", "-y",
        "-i", str(VOICE_FILE),
        "-i", str(BGM_FILE),
        "-filter_complex",
        (
            "[1:a]volume=1.0[bg];"
            "[0:a][bg]amix=inputs=2:"
            "duration=first:dropout_transition=2:"
            "normalize=0[out]"
        ),
        "-map", "[out]",
        "-c:a", "pcm_s16le",
        str(FINAL_FILE)
    ]

    run_command(command)


def main():
    if not VOICE_FILE.exists():
        raise FileNotFoundError(
            "Voiceover not found. Generate voiceover first."
        )

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    BGM_FILE.parent.mkdir(parents=True, exist_ok=True)

    paragraphs = read_script()
    scenes = make_scenes(paragraphs)

    total_duration = get_audio_duration()
    total_words = sum(scene["words"] for scene in scenes)

    print("Narration duration:", round(total_duration, 2), "seconds")
    print("Detected scenes:", len(scenes))

    segment_files = []

    elapsed = 0.0

    for index, scene in enumerate(scenes, 1):
        if index == len(scenes):
            duration = total_duration - elapsed
        else:
            duration = (
                total_duration * scene["words"] / total_words
            )

        elapsed += duration

        mood = scene["mood"]
        track = find_music(mood)

        output = TEMP_DIR / f"segment_{index:03d}.wav"

        print(
            f"Scene {index}/{len(scenes)} | "
            f"Mood: {mood} | "
            f"Duration: {duration:.1f}s | "
            f"Music: {track.name}"
        )

        create_music_segment(track, output, duration)
        segment_files.append(output)

    print("Joining background music...")
    join_segments(segment_files)

    print("Mixing narration and background music...")
    mix_voice_and_music()

    print("SUCCESS: Automatic BGM complete!")
    print("Final audio:", FINAL_FILE)


if __name__ == "__main__":
    main()
