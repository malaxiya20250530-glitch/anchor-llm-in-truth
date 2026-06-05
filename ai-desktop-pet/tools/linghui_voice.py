#!/usr/bin/env python3
"""
灵绘语音生成器 — 生成 WAV 问候语 + 歌单下载
纯 Python 标准库，零依赖
"""

import wave, struct, math, os, sys, urllib.request, json
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "preview" / "voice"
MUSIC_DIR = Path(__file__).parent.parent / "preview" / "music"

# ── 简易波表合成器 ──

SAMPLE_RATE = 22050

# 中文拼音 → 音高映射（简化版，按声调）
PHONEME_PITCH = {
    # 一声（高平）
    "ni": (260, 0.12), "hao": (280, 0.15), "wo": (290, 0.1),
    "shi": (300, 0.12), "ling": (310, 0.15), "hui": (320, 0.12),
    "ke": (280, 0.1), "yi": (300, 0.1), "chang": (310, 0.15),
    "ge": (290, 0.12), "tiao": (270, 0.12), "wu": (280, 0.1),
    "de": (260, 0.08),
    # 标点停顿
    "，": (0, 0.15), "！": (0, 0.2), "。": (0, 0.2),
}


def generate_sine_wave(freq: float, duration: float, amp: float = 0.6) -> list:
    """生成正弦波"""
    samples = int(SAMPLE_RATE * duration)
    data = []
    for i in range(samples):
        t = i / SAMPLE_RATE
        # 振幅包络（ADSR 简化）
        attack = min(1, t / 0.01)
        release = max(0, min(1, (duration - t) / 0.03))
        envelope = attack * release * amp

        # 基频 + 泛音
        value = math.sin(2 * math.pi * freq * t) * 0.6
        value += math.sin(2 * math.pi * freq * 2 * t) * 0.2
        value += math.sin(2 * math.pi * freq * 3 * t) * 0.1
        value *= envelope

        # 颤音
        vibrato = 1 + math.sin(2 * math.pi * 5 * t) * 0.005
        value *= vibrato

        data.append(value)
    return data


def text_to_waveform(text: str) -> tuple:
    """文本 → 波形数据"""
    # 切分为音节
    syllables = []
    i = 0
    while i < len(text):
        found = False
        for length in [2, 1]:
            chunk = text[i:i+length]
            if chunk in PHONEME_PITCH:
                syllables.append(chunk)
                i += length
                found = True
                break
        if not found:
            i += 1

    if not syllables:
        return [], ""

    # 生成波形
    all_samples = []
    for syl in syllables:
        freq, dur = PHONEME_PITCH.get(syl, (220, 0.1))
        if freq > 0:
            samples = generate_sine_wave(freq, dur, 0.5)
        else:
            # 停顿 → 静音
            samples = [0.0] * int(SAMPLE_RATE * dur)
        all_samples.extend(samples)

    # 实际语音文本（中文原样）
    return all_samples, text


def save_wav(filename: str, samples: list, text: str):
    """保存为 WAV 文件"""
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with wave.open(filename, "w") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.setnframes(len(samples))

        # 16-bit PCM
        packed = b""
        for s in samples:
            val = max(-32767, min(32767, int(s * 32767)))
            packed += struct.pack("<h", val)
        wav.writeframes(packed)

    size_kb = os.path.getsize(filename) / 1024
    print(f"  🎤 {filename} — {size_kb:.0f}KB — 「{text}」")


# ── 歌单下载 ──

FREE_SONGS = [
    {
        "title": "中国舞曲",
        "url": "https://freepd.com/music/Chinese%20Dance.mp3",
        "bpm": 110,
        "desc": "传统中国风舞曲 (CC0)",
        "mood": "elegant"
    },
    {
        "title": "史诗战歌",
        "url": "https://freepd.com/music/Epic%20Trailer.mp3",
        "bpm": 140,
        "desc": "史诗战斗配乐 (CC0)",
        "mood": "epic"
    },
    {
        "title": "宁静钢琴",
        "url": "https://freepd.com/music/Pensive%20Piano.mp3",
        "bpm": 80,
        "desc": "宁静钢琴独奏 (CC0)",
        "mood": "calm"
    },
    {
        "title": "欢快庆典",
        "url": "https://freepd.com/music/Celebration.mp3",
        "bpm": 120,
        "desc": "欢乐庆典音乐 (CC0)",
        "mood": "happy"
    },
    {
        "title": "神秘东方",
        "url": "https://freepd.com/music/Oriental%20Grove.mp3",
        "bpm": 95,
        "desc": "东方神秘氛围 (CC0)",
        "mood": "mysterious"
    },
    {
        "title": "爵士咖啡馆",
        "url": "https://freepd.com/music/Jazz%20Cafe.mp3",
        "bpm": 90,
        "desc": "轻松爵士背景 (CC0)",
        "mood": "relaxed"
    },
    {
        "title": "电子律动",
        "url": "https://freepd.com/music/Electro%20Swing.mp3",
        "bpm": 130,
        "desc": "现代电子摇摆 (CC0)",
        "mood": "energetic"
    },
    {
        "title": "古筝流水",
        "url": "https://freepd.com/music/GuZheng%20River.mp3",
        "bpm": 70,
        "desc": "古筝流水意境 (CC0)",
        "mood": "zen"
    },
]


def download_song(song: dict, output_dir: str) -> bool:
    """下载一首歌"""
    fname = song["title"] + ".mp3"
    path = os.path.join(output_dir, fname)

    if os.path.exists(path):
        print(f"  ✓ {fname} — 已缓存")
        return True

    try:
        print(f"  ⏳ 下载 {fname}...")
        req = urllib.request.Request(song["url"], headers={"User-Agent": "LingHui/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()
            with open(path, "wb") as f:
                f.write(data)
            print(f"  ✓ {fname} — {len(data)/1024:.0f}KB")
            return True
    except Exception as e:
        print(f"  ✗ {fname} — {e}")
        return False


# ── CLI ──

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="灵绘语音 + 歌单下载")
    parser.add_argument("--greeting", "-g", action="store_true", help="生成问候语音")
    parser.add_argument("--download", "-d", action="store_true", help="下载免费歌单")
    parser.add_argument("--all", "-a", action="store_true", help="全部执行")
    parser.add_argument("--text", "-t", default="", help="自定义文本合成")

    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MUSIC_DIR.mkdir(parents=True, exist_ok=True)

    print("🎤 灵绘语音系统")
    print()

    if args.greeting or args.all:
        phrases = [
            "你好，我是灵绘，可以唱歌跳舞的！",
            "想听什么歌？",
            "正在下载歌曲，请稍等",
            "看我的舞姿！",
            "燃烧吧！",
            "好的，马上播放",
            "下一首",
        ]
        for phrase in phrases:
            samples, text = text_to_waveform(phrase)
            if samples:
                fname = phrase[:6].replace("，", "").replace("！", "").replace("？", "")
                save_wav(str(OUTPUT_DIR / f"{fname}.wav"), samples, phrase)

    if args.text:
        samples, text = text_to_waveform(args.text)
        if samples:
            save_wav(str(OUTPUT_DIR / "custom.wav"), samples, args.text)

    if args.download or args.all:
        print("\n🎵 歌单下载")
        ok = 0
        for song in FREE_SONGS:
            if download_song(song, str(MUSIC_DIR)):
                ok += 1
        print(f"\n  {ok}/{len(FREE_SONGS)} 首就绪")

    print("\n完成 👋")
