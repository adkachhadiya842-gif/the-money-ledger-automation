import os
import re
import subprocess
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT_FILE = ROOT / "output" / "script.txt"
VOICE_FILE = ROOT / "output" / "voiceover.wav"
MUSIC_DIR = ROOT / "music"
INTRO_FILE = MUSIC_DIR / "intro" / "Uprising.mp3"
TEMP_DIR = ROOT / "output" / "bgm_segments"
BGM_FILE = ROOT / "output" / "background_music.wav"
FINAL_FILE = ROOT / "output" / "final_audio.wav"

def env_bool(name, default=True):
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")

BGM_ENABLED = env_bool("BGM_ENABLED", True)
INTRO_ENABLED = env_bool("INTRO_ENABLED", True)

BGM_VOLUME = 0.10
INTRO_VOLUME = 0.18
INTRO_SECONDS = 10
FADE_SECONDS = 1.5

MOOD_KEYWORDS = {
    "mystery": ["secret", "hidden", "mystery", "unknown", "shadow", "behind the scenes", "silently", "secretly"],
    "suspense": ["warning", "danger", "risk", "threat", "investigation", "question", "uncertain", "unexpected"],
    "crisis": ["crisis", "crash", "bankruptcy", "debt", "recession", "failure", "panic", "loss", "fraud", "scandal", "collapse", "disaster"],
    "growth": ["growth", "success", "profit", "innovation", "future", "opportunity", "wealth", "rise", "recovery", "expansion"],
    "revelation": ["revealed", "discovered", "truth", "reveal", "surprising", "what happened", "the reality", "the truth"]
}

def run_command(command):
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        raise RuntimeError("FFmpeg failed:\n" + result.stderr[-4000:])

def read_script():
    if not SCRIPT_FILE.exists():
        raise FileNotFoundError(f"Script not found: {SCRIPT_FILE}")
    text = SCRIPT_FILE.read_text(encoding="utf-8")
    text = re.split(r"FACT[- ]CHECK NOTES", text, flags=re.IGNORECASE)[0]
    text = re.sub(r"(?im)^\s*(TITLE|VISUAL|B-ROLL|ON-SCREEN|EDITOR NOTE|SOURCE NOTE|GRAPHICS|MUSIC)\s*:.*$", "", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if paragraphs and len(paragraphs[0].split()) < 12:
        paragraphs = paragraphs[1:]
    if not paragraphs:
        raise ValueError("No narration paragraphs found!")
    return paragraphs

def detect_mood(paragraph):
    text = paragraph.lower()
    scores = {mood: sum(text.count(word) for word in words) for mood, words in MOOD_KEYWORDS.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "neutral"

def make_scenes(paragraphs):
    scenes = []
    for paragraph in paragraphs:
        mood = detect_mood(paragraph)
        words = len(paragraph.split())
        if scenes and scenes[-1]["mood"] == mood:
            scenes[-1]["text"] += "\n\n" + paragraph
            scenes[-1]["words"] += words
        else:
            scenes.append({"mood": mood, "text": paragraph, "words": words})
    return scenes

def get_audio_duration():
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(VOICE_FILE)],
        capture_output=True, text=True, check=True
    )
    return float(result.stdout.strip())

def find_music(mood):
    folder = MUSIC_DIR / mood
    files = [p for p in folder.iterdir() if p.suffix.lower() in (".mp3", ".wav", ".m4a", ".ogg")] if folder.exists() else []
    if not files and mood != "neutral":
        print(f"No {mood} music found. Using neutral music.")
        return find_music("neutral")
    if not files:
        raise FileNotFoundError(f"No music files found in {folder}")
    return random.choice(files)

def create_music_segment(track, output, duration):
    if duration <= 0:
        raise ValueError("Invalid music segment duration")
    fade = min(FADE_SECONDS, duration / 3)
    fade_out_start = max(0, duration - fade)
    audio_filter = f"volume={BGM_VOLUME},afade=t=in:st=0:d={fade},afade=t=out:st={fade_out_start}:d={fade}"
    run_command([
        "ffmpeg", "-y", "-stream_loop", "-1", "-i", str(track),
        "-t", f"{duration:.3f}", "-af", audio_filter,
        "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(output)
    ])

def join_segments(segment_files):
    concat_file = TEMP_DIR / "concat.txt"
    with concat_file.open("w", encoding="utf-8") as f:
        for segment in segment_files:
            safe_path = segment.resolve().as_posix().replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")
    run_command([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c:a", "pcm_s16le", str(BGM_FILE)
    ])

def create_silence(output, duration):
    run_command([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", f"{duration:.3f}", "-ar", "44100", "-ac", "2",
        "-c:a", "pcm_s16le", str(output)
    ])

def add_intro_music(base_file, total_duration):
    intro_duration = min(INTRO_SECONDS, total_duration)
    fade_in = min(1.5, intro_duration / 3)
    fade_out = min(2.0, intro_duration / 3)
    fade_out_start = max(0.0, intro_duration - fade_out)
    filt = (
        f"[1:a]atrim=duration={intro_duration:.3f},asetpts=PTS-STARTPTS,"
        f"volume={INTRO_VOLUME},afade=t=in:st=0:d={fade_in:.3f},"
        f"afade=t=out:st={fade_out_start:.3f}:d={fade_out:.3f}[intro];"
        "[0:a][intro]amix=inputs=2:duration=first:normalize=0[out]"
    )
    output = TEMP_DIR / "bgm_with_intro.wav"
    run_command([
        "ffmpeg", "-y", "-i", str(base_file), "-stream_loop", "-1", "-i", str(INTRO_FILE),
        "-filter_complex", filt, "-map", "[out]", "-ar", "44100", "-ac", "2",
        "-c:a", "pcm_s16le", str(output)
    ])
    return output

def mix_voice_and_music(background_file):
    run_command([
        "ffmpeg", "-y", "-i", str(VOICE_FILE), "-i", str(background_file),
        "-filter_complex",
        "[0:a]volume=1.0[voice];[1:a]volume=1.0[bg];"
        "[voice][bg]amix=inputs=2:duration=first:dropout_transition=2:normalize=0[out]",
        "-map", "[out]", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(FINAL_FILE)
    ])

def main():
    if not VOICE_FILE.exists():
        raise FileNotFoundError("Voiceover not found. Generate voiceover first.")
    if INTRO_ENABLED and not INTRO_FILE.exists():
        raise FileNotFoundError(f"Intro music enabled, but file not found: {INTRO_FILE}")

    TEMP_DIR.mkdir(parents=True, exist_ok=True)
    BGM_FILE.parent.mkdir(parents=True, exist_ok=True)
    total_duration = get_audio_duration()

    print("Narration duration:", round(total_duration, 2), "seconds")
    print("Background music:", "ON" if BGM_ENABLED else "OFF")
    print("Intro music:", "ON" if INTRO_ENABLED else "OFF")

    if BGM_ENABLED:
        scenes = make_scenes(read_script())
        total_words = sum(scene["words"] for scene in scenes)
        if total_words == 0:
            raise ValueError("Script contains no usable narration words.")
        print("Detected music scenes:", len(scenes))
        segment_files = []
        elapsed = 0.0
        for index, scene in enumerate(scenes, 1):
            duration = total_duration - elapsed if index == len(scenes) else total_duration * scene["words"] / total_words
            elapsed += duration
            mood = scene["mood"]
            track = find_music(mood)
            output = TEMP_DIR / f"segment_{index:03d}.wav"
            print(f"Scene {index}/{len(scenes)} | Mood: {mood} | Duration: {duration:.1f}s | Music: {track.name}")
            create_music_segment(track, output, duration)
            segment_files.append(output)
        print("Joining mood-based background music...")
        join_segments(segment_files)
    else:
        print("BGM disabled. Creating silent background track.")
        create_silence(BGM_FILE, total_duration)

    background_file = add_intro_music(BGM_FILE, total_duration) if INTRO_ENABLED else BGM_FILE
    print("Mixing narration with selected music...")
    mix_voice_and_music(background_file)
    print("SUCCESS: Audio generation complete!")
    print("Background music file:", BGM_FILE)
    print("Final audio file:", FINAL_FILE)

if __name__ == "__main__":
    main()
