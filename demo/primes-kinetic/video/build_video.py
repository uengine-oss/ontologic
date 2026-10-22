#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""정지화면 + 나레이션 음성을 하나의 영상으로 합친다.

장면 길이는 `narration/durations.json` 의 음성 길이를 그대로 쓴다. 한 장면이 여러 장이면
그 길이를 균등하게 나눈다. 벽시계에 기대지 않으므로 머신이 아무리 바빠도 결과가 같다.
"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
V = ROOT
SL = os.path.join(V, "slides")
NAR = os.path.join(V, "narration")
OUT = os.path.join(V, "PriMES-커맨드-반복수주-시연.mp4")
PAD = 0.45          # 장면 사이 여유 (음성 끝나고 바로 넘어가면 숨 가쁘다)


def main():
    dur = {d["scene"]: float(d["duration"]) for d in json.load(open(f"{NAR}/durations.json"))}
    slides = json.load(open(f"{V}/slides.json"))
    missing = [s["scene"] for s in slides if s["scene"] not in dur]
    if missing:
        sys.exit(f"음성이 없는 장면: {missing}")

    # ── 1) 영상 트랙 : concat demuxer ──────────────────────────────────────
    lines, total = [], 0.0
    for s in slides:
        n = len(s["files"])
        each = (dur[s["scene"]] + PAD) / n
        for f in s["files"]:
            lines.append(f"file '{os.path.join(SL, f)}'")
            lines.append(f"duration {each:.3f}")
            total += each
    lines.append(f"file '{os.path.join(SL, slides[-1]['files'][-1])}'")   # concat 규약: 마지막 한 번 더
    open(f"{V}/concat.txt", "w").write("\n".join(lines) + "\n")

    # ── 2) 음성 트랙 : 장면마다 PAD 만큼 무음을 덧대어 이어 붙인다 ──────────
    parts = []
    for s in slides:
        w = f"{NAR}/scene-{s['scene']:02d}.wav"
        if not os.path.exists(w):
            sys.exit(f"음성 파일 없음: {w}")
        parts.append(w)
    filt = "".join(f"[{i}:a]apad=pad_dur={PAD}[a{i}];" for i in range(len(parts)))
    filt += "".join(f"[a{i}]" for i in range(len(parts))) + f"concat=n={len(parts)}:v=0:a=1[out]"
    cmd_a = ["ffmpeg", "-y"] + sum([["-i", p] for p in parts], []) + \
            ["-filter_complex", filt, "-map", "[out]", f"{V}/narration.m4a"]
    run(cmd_a, "음성 합치기")

    # ── 3) 영상 + 음성 ────────────────────────────────────────────────────
    cmd_v = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"{V}/concat.txt",
             "-i", f"{V}/narration.m4a",
             "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                    "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color=0x0b1018,fps=30,format=yuv420p",
             "-c:v", "libx264", "-preset", "medium", "-crf", "20",
             "-c:a", "aac", "-b:a", "160k", "-shortest", "-movflags", "+faststart", OUT]
    run(cmd_v, "영상 합성")

    write_srt(slides, dur)
    d = probe(OUT)
    print(f"\n완성 : {OUT}")
    print(f"  길이 {d//60:.0f}분 {d%60:04.1f}초 · 장면 {len(slides)}개 · 이미지 "
          f"{sum(len(s['files']) for s in slides)}장 · {os.path.getsize(OUT)/1e6:.1f} MB")
    print(f"  (영상 트랙 계산값 {total:.1f}초 · 음성 {probe(f'{V}/narration.m4a'):.1f}초)")


def write_srt(slides, dur):
    """나레이션 문장을 장면 시간에 맞춘 자막 파일. 굽지 않고 옆에 둔다 (libass 없는 ffmpeg 대비)."""
    text = {n["scene"]: n["text"] for n in json.load(open(f"{V}/narration.json"))}
    fmt = lambda t: f"{int(t//3600):02d}:{int(t%3600//60):02d}:{int(t%60):02d},{int(t*1000%1000):03d}"
    out, t = [], 0.0
    for i, s in enumerate(slides, 1):
        d = dur[s["scene"]]
        out.append(f"{i}\n{fmt(t)} --> {fmt(t + d)}\n{text[s['scene']]}\n")
        t += d + PAD
    open(OUT.replace(".mp4", ".srt"), "w").write("\n".join(out))


def run(cmd, label):
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode:
        sys.exit(f"{label} 실패:\n{p.stderr[-1500:]}")
    print(f"  {label} 완료")


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "default=noprint_wrappers=1:nokey=1", path],
                         capture_output=True, text=True).stdout.strip()
    return float(out or 0)


if __name__ == "__main__":
    main()
