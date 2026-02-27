#!/usr/bin/env python3
"""
ElevenLabs TTS 音声生成ツール
キャラ名とセリフをコピペ → 自動でキャラごとのvoice_idに紐づけ → 音声生成
"""
import json
import os
import re
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

from parser import parse_dialogue, DialogueLine


def sanitize_filename(text: str, max_length: int = 200) -> str:
    """ファイル名に使えない文字を除去"""
    sanitized = re.sub(r'[\\/:*?"<>|\n\r\t]', '', text)
    sanitized = sanitized.replace(' ', '_')
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized


def load_config(config_path: str = "config.json") -> dict:
    """設定ファイルを読み込む"""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_voice_id(character: str, config: dict) -> str | None:
    """キャラ名からvoice_idを取得"""
    return config.get("character_voices", {}).get(character)


def generate_audio(
    client: ElevenLabs,
    text: str,
    voice_id: str,
    model_id: str = "eleven_v3",
    output_format: str = "mp3_44100_128",
    language_code: str = "ja",
    previous_text: str | None = None,
    next_text: str | None = None,
) -> bytes:
    """ElevenLabs APIで音声を生成"""
    kwargs = {
        "text": text,
        "voice_id": voice_id,
        "model_id": model_id,
        "output_format": output_format,
        "language_code": language_code,
    }
    
    if previous_text:
        kwargs["previous_text"] = previous_text
    if next_text:
        kwargs["next_text"] = next_text
    
    audio = client.text_to_speech.convert(**kwargs)
    
    # ストリームをバイトに変換
    audio_bytes = b""
    for chunk in audio:
        audio_bytes += chunk
    
    return audio_bytes


def save_audio(audio_bytes: bytes, filepath: str) -> None:
    """音声ファイルを保存"""
    with open(filepath, 'wb') as f:
        f.write(audio_bytes)


def process_dialogues(
    dialogues: list[DialogueLine],
    config: dict,
    client: ElevenLabs,
    output_dir: str,
    use_context: bool = True,
    delay: float = 0.5,
) -> list[dict]:
    """複数のセリフを処理して音声生成"""
    results = []
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    model_id = config.get("default_model", "eleven_v3")
    output_format = config.get("default_output_format", "mp3_44100_128")
    language_code = config.get("language_code", "ja")
    
    for i, dialogue in enumerate(dialogues):
        voice_id = get_voice_id(dialogue.character, config)
        
        if not voice_id:
            print(f"[SKIP] voice_id not found: {dialogue.character}")
            results.append({
                "index": dialogue.index,
                "character": dialogue.character,
                "status": "skipped",
                "reason": "voice_id not found",
            })
            continue
        
        # 前後のコンテキスト（同じキャラの場合のみ有効）
        # 注意: eleven_v3モデルはprevious_text/next_textに非対応
        previous_text = None
        next_text = None
        
        if use_context and model_id != "eleven_v3":
            if i > 0 and dialogues[i - 1].character == dialogue.character:
                previous_text = dialogues[i - 1].text
            if i < len(dialogues) - 1 and dialogues[i + 1].character == dialogue.character:
                next_text = dialogues[i + 1].text
        
        try:
            print(f"[{dialogue.index:03d}] Generating: {dialogue.character} ({dialogue.char_count}字)...")
            
            audio_bytes = generate_audio(
                client=client,
                text=dialogue.text,
                voice_id=voice_id,
                model_id=model_id,
                output_format=output_format,
                language_code=language_code,
                previous_text=previous_text,
                next_text=next_text,
            )
            
            # ファイル名: 1_キャラ名_セリフ内容.mp3
            text_content = sanitize_filename(dialogue.text)
            filename = f"{dialogue.index}_{dialogue.character}_{text_content}.mp3"
            filepath = output_path / filename
            save_audio(audio_bytes, str(filepath))
            
            print(f"    -> Saved: {filename}")
            
            results.append({
                "index": dialogue.index,
                "character": dialogue.character,
                "status": "success",
                "filepath": str(filepath),
            })
            
            # レート制限対策
            if i < len(dialogues) - 1:
                time.sleep(delay)
                
        except Exception as e:
            print(f"[ERROR] {dialogue.character}: {e}")
            results.append({
                "index": dialogue.index,
                "character": dialogue.character,
                "status": "error",
                "reason": str(e),
            })
    
    return results


def main(auto_confirm: bool = False):
    """メイン処理"""
    load_dotenv()
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("Error: ELEVENLABS_API_KEY not found in environment variables")
        print("Please create a .env file with your API key")
        sys.exit(1)
    
    config = load_config()
    client = ElevenLabs(api_key=api_key)
    
    print("=" * 60)
    print("ElevenLabs TTS Generator")
    print("=" * 60)
    print("\n台本テキストを入力してください（入力完了後、空行でEnterを2回押す）:\n")
    
    # 複数行入力を受け付ける
    lines = []
    empty_count = 0
    
    while True:
        try:
            line = input()
            if line == "":
                empty_count += 1
                if empty_count >= 2:
                    break
                lines.append(line)
            else:
                empty_count = 0
                lines.append(line)
        except EOFError:
            break
    
    input_text = "\n".join(lines)
    
    if not input_text.strip():
        print("Error: No input provided")
        sys.exit(1)
    
    # パース
    dialogues = parse_dialogue(input_text)
    
    if not dialogues:
        print("Error: No dialogues found in input")
        sys.exit(1)
    
    print(f"\n{len(dialogues)} 件のセリフを検出しました:\n")
    for d in dialogues:
        voice_id = get_voice_id(d.character, config)
        status = "✓" if voice_id else "✗ (voice_id未設定)"
        print(f"  {d.index:03d}. [{d.character}] {status}")
    
    print(f"\n出力先: {config.get('output_directory', './output/')}")
    
    if not auto_confirm:
        print("\n生成を開始しますか？ [y/N]: ", end="")
        confirm = input().strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            sys.exit(0)
    
    print("\n" + "-" * 60)
    print("音声生成を開始します...")
    print("-" * 60 + "\n")
    
    output_dir = config.get("output_directory", "./output/")
    results = process_dialogues(dialogues, config, client, output_dir)
    
    # サマリー
    print("\n" + "=" * 60)
    print("完了サマリー")
    print("=" * 60)
    
    success = sum(1 for r in results if r["status"] == "success")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    errors = sum(1 for r in results if r["status"] == "error")
    
    print(f"  成功: {success}")
    print(f"  スキップ: {skipped}")
    print(f"  エラー: {errors}")
    print(f"  合計: {len(results)}")
    
    if skipped > 0:
        print("\nスキップされたキャラ:")
        for r in results:
            if r["status"] == "skipped":
                print(f"  - {r['character']}: {r['reason']}")
    
    if errors > 0:
        print("\nエラー:")
        for r in results:
            if r["status"] == "error":
                print(f"  - {r['character']}: {r['reason']}")


def list_voices():
    """登録済みボイス一覧を表示"""
    load_dotenv()
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("Error: ELEVENLABS_API_KEY not found")
        sys.exit(1)
    
    client = ElevenLabs(api_key=api_key)
    
    print("Fetching voices from ElevenLabs...")
    response = client.voices.get_all()
    
    print(f"\n{len(response.voices)} voices found:\n")
    for voice in response.voices:
        print(f"  {voice.name}: {voice.voice_id}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--list-voices":
        list_voices()
    elif len(sys.argv) > 1 and sys.argv[1] == "-y":
        main(auto_confirm=True)
    else:
        main()
