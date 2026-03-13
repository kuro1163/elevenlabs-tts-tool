#!/usr/bin/env python3
"""前後コンテキストあり/なしの比較テスト"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from generate import generate_audio, load_config, get_voice_id, sanitize_filename
from parser import DialogueLine

# テスト台本（31-38）
DIALOGUES = [
    DialogueLine(index=31, character="チヒロ", text="どう？味のほうは", char_count=8),
    DialogueLine(index=32, character="先生", text="う、うん、美味しいよ。ありがとう2人とも", char_count=19),
    DialogueLine(index=33, character="キリノ", text="それはよかったです！", char_count=10),
    DialogueLine(index=34, character="キリノ", text="先生はお酒が好きだと聞いていたので絶対喜んでくれると思っていました！", char_count=31),
    DialogueLine(index=35, character="チヒロ", text="へぇ、初めて聞いた。そうなの？", char_count=14),
    DialogueLine(index=36, character="先生", text="え？いや、そうでもないし、むしろ弱", char_count=16),
    DialogueLine(index=37, character="先生", text="というかそんな情報どこで", char_count=11),
    DialogueLine(index=38, character="先生", text="？誰からだろう", char_count=7),
]


def main():
    load_dotenv()
    api_key = os.getenv("ELEVENLABS_API_KEY")
    config = load_config()
    client = ElevenLabs(api_key=api_key)

    out_no_ctx = Path("output/test_no_context")
    out_ctx = Path("output/test_with_context")
    out_no_ctx.mkdir(parents=True, exist_ok=True)
    out_ctx.mkdir(parents=True, exist_ok=True)

    dialogues = DIALOGUES

    for i, d in enumerate(dialogues):
        voice_id = get_voice_id(d.character, config)
        if not voice_id:
            print(f"[SKIP] {d.character}: voice_id not found")
            continue

        fname = f"{d.index}_{d.character}_{sanitize_filename(d.text)}.mp3"

        # --- v3 (コンテキスト非対応) ---
        print(f"[{d.index:03d}] {d.character} (v3 / コンテキストなし)...")
        audio = generate_audio(client, d.text, voice_id, model_id="eleven_v3")
        with open(out_no_ctx / fname, 'wb') as f:
            f.write(audio)

        # --- multilingual_v2 + コンテキストあり ---
        prev_text = None
        next_text = None
        if i > 0:
            prev = dialogues[i - 1]
            prev_text = f"{prev.character}「{prev.text}」" if prev.character != d.character else prev.text
        if i < len(dialogues) - 1:
            nxt = dialogues[i + 1]
            next_text = f"{nxt.character}「{nxt.text}」" if nxt.character != d.character else nxt.text

        print(f"[{d.index:03d}] {d.character} (v2 + コンテキスト)...")
        if prev_text:
            print(f"    prev: {prev_text[:50]}")
        if next_text:
            print(f"    next: {next_text[:50]}")
        audio = generate_audio(client, d.text, voice_id,
                               model_id="eleven_multilingual_v2",
                               previous_text=prev_text, next_text=next_text)
        with open(out_ctx / fname, 'wb') as f:
            f.write(audio)

        print(f"    -> OK")

    print(f"\n比較用ファイル出力:")
    print(f"  コンテキストなし: {out_no_ctx}")
    print(f"  コンテキストあり: {out_ctx}")


if __name__ == '__main__':
    main()
