#!/usr/bin/env python3
"""데모 영상 조립 — 화면 녹화(webm) + 한국어 내레이션(TTS) + 타이틀 카드 → MP4 한 편.

내레이션은 **OpenAI TTS**(`gpt-4o-mini-tts`)로 만든다. `instructions` 로 낭독 톤을 지정할 수
있어서 기계 낭독조를 피할 수 있다. 키가 없으면 macOS `say` 로 떨어진다.

주의: 이 키는 **내레이션에만** 쓴다. 데모 실행 자체(에이전트·MCP)는 여전히 API 키를 쓰지
않는다 — 그것이 시연의 요점이다 (spec 004).

  단계
  1. narration.json 의 각 장면 문장을 TTS 로 합성 → 문장별 길이 측정 → 장면 오디오 결합
  2. 장면 타이틀 카드(PNG)를 만들어 3초 클립으로
  3. 화면 녹화 클립을 장면 오디오 길이에 맞춰 늘리거나 잘라 붙임
  4. 타이틀 카드 + 본편을 이어 붙이고 자막(SRT) 을 함께 낸다

  uv run --with pillow python demo/scm-agent/build_video.py
"""
from __future__ import annotations

import json
import shutil
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
VIDEO = HERE / "video"
RAW = VIDEO / "raw"
AUDIO = VIDEO / "audio"
CARDS = VIDEO / "cards"
WORK = VIDEO / "work"
OUT = VIDEO / "SCM-Agent-Suite-데모.mp4"
SRT = VIDEO / "SCM-Agent-Suite-데모.srt"

W, H = 1600, 900
FONT_CANDIDATES = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/Library/Fonts/AppleGothic.ttf",
]


def run(*args, **kw):
    return subprocess.run(args, check=True, capture_output=True, text=True, **kw)


def duration(path: Path) -> float:
    out = run("ffprobe", "-v", "error", "-show_entries", "format=duration",
              "-of", "default=nw=1:nk=1", str(path)).stdout.strip()
    return float(out)


#: 내레이션 톤. OpenAI TTS 는 `instructions` 로 낭독 스타일을 받는다 — 목소리 선택만으로는
#: 사무적인 낭독이 되기 쉬워서, 데모 영상에 맞는 밝고 자연스러운 톤을 명시한다.
TTS_INSTRUCTIONS = (
    "밝고 자연스러운 톤으로, 기술 데모를 소개하는 전문 발표자처럼 읽어 주세요. "
    "너무 빠르지 않게, 문장 끝을 또렷하게 맺고, 숫자와 제품명은 정확하게 발음해 주세요. "
    "딱딱한 뉴스 낭독조가 아니라 청중에게 설명하듯 친근하게."
)


def synth_openai(text: str, dest: Path, voice: str, model: str, api_key: str) -> float:
    """OpenAI TTS 로 합성한다. 실패하면 예외를 올린다 — 조용히 다른 목소리로 바뀌면 안 된다."""

    import urllib.error
    import urllib.request

    body = json.dumps({
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": "wav",
        "instructions": TTS_INSTRUCTIONS,
    }).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    raw = dest.with_suffix(".raw.wav")
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                raw.write_bytes(response.read())
            break
        except urllib.error.HTTPError as exc:          # 429·5xx 는 재시도할 값어치가 있다
            last_error = exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise
        except urllib.error.URLError as exc:
            last_error = exc
            if attempt == 2:
                raise
        time.sleep(2 * (attempt + 1))
    else:                                              # pragma: no cover
        raise RuntimeError(f"TTS 실패: {last_error}")

    # 24kHz 모노로 오므로 영상 오디오 규격(48kHz 스테레오)으로 맞춘다.
    run("ffmpeg", "-y", "-i", str(raw), "-ar", "48000", "-ac", "2", str(dest))
    raw.unlink(missing_ok=True)
    return duration(dest)


def synth_say(text: str, dest: Path, voice: str, rate: int) -> float:
    """macOS `say` 폴백. 키가 없을 때만 쓴다."""

    aiff = dest.with_suffix(".aiff")
    run("say", "-v", voice, "-r", str(rate), "-o", str(aiff), text)
    run("ffmpeg", "-y", "-i", str(aiff), "-ar", "48000", "-ac", "2", str(dest))
    aiff.unlink(missing_ok=True)
    return duration(dest)


def font():
    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return f
    return None


def make_card(title: str, subtitle: str, dest: Path):
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (W, H), (11, 15, 25))
    d = ImageDraw.Draw(img)
    fpath = font()
    ft = ImageFont.truetype(fpath, 62) if fpath else ImageFont.load_default()
    fs = ImageFont.truetype(fpath, 32) if fpath else ImageFont.load_default()
    # 상단 강조선
    d.rectangle([0, 0, W, 6], fill=(129, 140, 248))

    def center(text, f, y, fill):
        bbox = d.textbbox((0, 0), text, font=f)
        d.text(((W - (bbox[2] - bbox[0])) / 2, y), text, font=f, fill=fill)

    center(title, ft, H / 2 - 90, (233, 237, 247))
    for i, line in enumerate(subtitle.split("\n")):
        center(line, fs, H / 2 + 20 + i * 48, (148, 163, 184))
    img.save(dest)


def card_clip(png: Path, seconds: float, dest: Path):
    run("ffmpeg", "-y", "-loop", "1", "-i", str(png), "-t", f"{seconds:.2f}",
        "-vf", f"scale={W}:{H},format=yuv420p", "-r", "25", "-c:v", "libx264",
        "-preset", "medium", "-crf", "20", str(dest))


def make_badge(text: str, dest: Path):
    """우상단 배지를 PNG 로 그린다.

    ffmpeg 의 `drawtext` 는 libfreetype 이 빠진 빌드에서 없다. 배지를 이미지로 만들어
    `overlay` 로 얹으면 빌드 옵션에 기대지 않는다.
    """
    from PIL import Image, ImageDraw, ImageFont

    fpath = font()
    f = ImageFont.truetype(fpath, 26) if fpath else ImageFont.load_default()
    probe = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    box = probe.textbbox((0, 0), text, font=f)
    w, h = box[2] - box[0] + 32, box[3] - box[1] + 22
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=8, fill=(0, 0, 0, 130))
    d.text((16 - box[0], 11 - box[1]), text, font=f, fill=(255, 255, 255, 220))
    img.save(dest)
    return dest


def fit_video(src: Path, seconds: float, dest: Path, badge_dir: Path):
    """화면 녹화를 내레이션 길이에 맞춘다.

    잘라내지 않는다 — 앞부분만 남기면 화면 로딩과 질문 입력만 보이고 정작 답변이 사라진다.
    녹화가 길면 **배속**해서 장면 전체(질문 → 도구 호출 → 답변 → 스크롤)를 담고, 배속했다는
    사실을 화면에 표시한다. 녹화가 짧으면 마지막 프레임을 늘려 채운다.
    """
    have = duration(src)
    base = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=decrease,"
            f"pad={W}:{H}:(ow-iw)/2:(oh-ih)/2")
    if have > seconds * 1.02:
        factor = have / seconds
        label = f"실제 실행 화면 · {factor:.1f}배속" if factor >= 1.2 else "실제 실행 화면"
        chain = f"{base},setpts=PTS/{factor:.4f},format=yuv420p[v]"
    else:
        pad = max(0.0, seconds - have)
        label = "실제 실행 화면"
        chain = f"{base},format=yuv420p,tpad=stop_mode=clone:stop_duration={pad:.2f}[v]"

    badge = make_badge(label, badge_dir / f"{dest.stem}-badge.png")
    run("ffmpeg", "-y", "-i", str(src), "-i", str(badge),
        "-filter_complex", f"{chain};[v][1:v]overlay=W-w-28:H-h-26:format=auto,format=yuv420p[out]",
        "-map", "[out]", "-t", f"{seconds:.2f}", "-r", "25", "-an",
        "-c:v", "libx264", "-preset", "medium", "-crf", "20", str(dest))


def srt_time(t: float) -> str:
    h = int(t // 3600); m = int(t % 3600 // 60); s = t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def main() -> int:
    for d in (AUDIO, CARDS, WORK):
        d.mkdir(parents=True, exist_ok=True)
    spec = json.loads((HERE / "narration.json").read_text(encoding="utf-8"))
    # 내레이션 엔진: OpenAI TTS 가 기본, 키가 없으면 macOS `say` 로 떨어진다.
    # 루트 `.env` 하나만 읽는다 (constitution VI).
    for line in (HERE.parents[1] / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("OPENAI_API_KEY=") and "OPENAI_API_KEY" not in os.environ:
            os.environ["OPENAI_API_KEY"] = line.split("=", 1)[1].strip()
    api_key = os.environ.get("OPENAI_API_KEY", "")
    tts = spec.get("tts", {})
    engine = tts.get("engine", "openai" if api_key else "say")
    # 키가 있어도 **살아 있는지**는 별개다. 만료된 키로 시작하면 첫 문장에서 401 로 죽는데,
    # 그때는 이미 장면 몇 개를 합성한 뒤라 되돌리기가 번거롭다. 한 번 찔러 보고 정한다.
    if engine == "openai" and api_key:
        import urllib.error
        import urllib.request as _rq
        probe = _rq.Request("https://api.openai.com/v1/models",
                            headers={"Authorization": f"Bearer {api_key}"})
        try:
            with _rq.urlopen(probe, timeout=20):
                pass
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                print(f"  [경고] OPENAI_API_KEY 가 거부되었습니다(HTTP {exc.code}). "
                      f"macOS `say` 로 합성합니다 — 키를 갱신하면 이 스크립트만 다시 돌리면 됩니다.")
                engine = "say"
            else:
                raise
        except Exception as exc:                              # 네트워크 문제도 같은 판단
            print(f"  [경고] OpenAI 에 닿지 못했습니다({exc}). macOS `say` 로 합성합니다.")
            engine = "say"
    oa_voice = tts.get("voice", "nova")
    oa_model = tts.get("model", "gpt-4o-mini-tts")
    voice, rate = spec.get("voice", "Yuna"), spec.get("rate", 180)
    if engine == "openai" and not api_key:
        print("  [경고] OPENAI_API_KEY 가 없습니다. macOS `say` 로 합성합니다.")
        engine = "say"
    print(f"내레이션: {engine}" + (f" · {oa_model} · {oa_voice}" if engine == "openai" else f" · {voice}"))

    def synth(text, dest):
        if engine == "openai":
            return synth_openai(text, dest, oa_voice, oa_model, api_key)
        return synth_say(text, dest, voice, rate)

    segments = []      # (video_path, audio_path, duration)
    subs = []          # (start, end, text)
    clock = 0.0

    for scene in spec["scenes"]:
        sid = scene["id"]
        # 1) 문장별 TTS
        parts, part_durs = [], []
        for i, line in enumerate(scene["lines"]):
            wav = AUDIO / f"{sid}-{i:02d}.wav"
            part_durs.append(synth(line, wav))
            parts.append(wav)
        # 문장 사이 0.45초 숨
        gap = AUDIO / "_gap.wav"
        if not gap.exists():
            run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
                "-t", "0.45", str(gap))
        listfile = WORK / f"{sid}-audio.txt"
        seq = []
        for p in parts:
            seq += [p, gap]
        listfile.write_text("".join(f"file '{p}'\n" for p in seq), encoding="utf-8")
        scene_audio = AUDIO / f"{sid}.wav"
        run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(listfile), "-c", "copy", str(scene_audio))
        adur = duration(scene_audio)

        # 자막 타임코드 (문장 + 갭 누적)
        t = clock
        card_secs = 3.0 if sid in ("intro", "outro") else 2.6
        t += card_secs
        for line, d_ in zip(scene["lines"], part_durs):
            subs.append((t, t + d_, line))
            t += d_ + 0.45

        # 2) 타이틀 카드
        png = CARDS / f"{sid}.png"
        subtitle = {"intro": "온톨로지 스튜디오 · 실제 실행 기록",
                    "outro": "6개 도메인 · 6/6 통과 · 도구 오류 0"}.get(sid, "실행 화면 — 재연 아님")
        make_card(scene["title"], subtitle, png)
        card_mp4 = WORK / f"{sid}-card.mp4"
        card_clip(png, card_secs, card_mp4)
        card_wav = AUDIO / f"{sid}-card.wav"
        run("ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", f"{card_secs:.2f}", str(card_wav))
        segments.append((card_mp4, card_wav, card_secs))
        clock += card_secs

        # 3) 본편 영상 (녹화가 없는 intro/outro 는 카드를 늘려 쓴다)
        src = RAW / f"{sid}.webm"
        body = WORK / f"{sid}-body.mp4"
        if src.exists():
            fit_video(src, adur, body, WORK)
        else:
            card_clip(png, adur, body)
        segments.append((body, scene_audio, adur))
        clock += adur

    # 4) 이어 붙이기
    concat_v = WORK / "video.txt"
    concat_a = WORK / "audio.txt"
    concat_v.write_text("".join(f"file '{v}'\n" for v, _, _ in segments), encoding="utf-8")
    concat_a.write_text("".join(f"file '{a}'\n" for _, a, _ in segments), encoding="utf-8")
    vcat = WORK / "video.mp4"
    acat = WORK / "audio.wav"
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_v), "-c", "copy", str(vcat))
    run("ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_a), "-c", "copy", str(acat))
    run("ffmpeg", "-y", "-i", str(vcat), "-i", str(acat), "-c:v", "copy", "-c:a", "aac",
        "-b:a", "192k", "-shortest", str(OUT))

    # 5) 자막
    lines = []
    for i, (start, end, text) in enumerate(subs, 1):
        lines += [str(i), f"{srt_time(start)} --> {srt_time(end)}", text, ""]
    SRT.write_text("\n".join(lines), encoding="utf-8")

    total = duration(OUT)
    print(f"완성: {OUT}  ({int(total // 60)}분 {int(total % 60)}초)")
    print(f"자막: {SRT}  ({len(subs)}개)")
    return 0


if __name__ == "__main__":
    if not shutil.which("ffmpeg"):
        print("ffmpeg 이 필요합니다.", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(main())
