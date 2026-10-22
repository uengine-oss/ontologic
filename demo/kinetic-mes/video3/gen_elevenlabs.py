#!/usr/bin/env python3
"""ElevenLabs 나레이션 — narration.json → narration/scene-NN.wav + durations.json (build_video.py 입력 형식).

키는 env ELEVENLABS_API_KEY 로만 받는다 (파일에 남기지 않는다). 목소리는 env ELEVENLABS_VOICE_ID.
"""
import json, os, subprocess, sys, urllib.request

KEY = os.environ.get("ELEVENLABS_API_KEY") or sys.exit("ELEVENLABS_API_KEY 가 없다")
VOICE = os.environ.get("ELEVENLABS_VOICE_ID") or sys.exit("ELEVENLABS_VOICE_ID 가 없다")
MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
OUT = "narration"
os.makedirs(OUT, exist_ok=True)


def tts(text: str, mp3: str) -> None:
    req = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}?output_format=mp3_44100_128",
        data=json.dumps({"text": text, "model_id": MODEL,
                         "voice_settings": {"stability": 0.5, "similarity_boost": 0.8, "style": 0.15,
                                            "use_speaker_boost": True}}).encode(),
        headers={"xi-api-key": KEY, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    with urllib.request.urlopen(req, timeout=120) as r, open(mp3, "wb") as f:
        f.write(r.read())


def duration(path: str) -> float:
    return float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                                 "default=noprint_wrappers=1:nokey=1", path], capture_output=True, text=True).stdout)


durs = []
for s in json.load(open("narration.json")):
    n = s["scene"]
    mp3, wav = f"{OUT}/scene-{n:02d}.mp3", f"{OUT}/scene-{n:02d}.wav"
    if not os.path.exists(mp3) or os.environ.get("FORCE"):
        tts(s["text"], mp3)
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", mp3, "-ar", "24000", "-ac", "1", wav], check=True)
    d = duration(wav)
    durs.append({"scene": n, "duration": d})
    print(f"[{n}] {d:.2f}s", flush=True)
json.dump(durs, open(f"{OUT}/durations.json", "w"), indent=1)
print(f"완료 — 총 {sum(x['duration'] for x in durs):.1f}s")
