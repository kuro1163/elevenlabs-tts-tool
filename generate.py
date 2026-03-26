#!/usr/bin/env python3
"""
ElevenLabs TTS 音声生成ツール
キャラ名とセリフをコピペ → 自動でキャラごとのvoice_idに紐づけ → 音声生成
"""
import json
import os
import re
import shutil
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs
from elevenlabs.types import PronunciationDictionaryVersionLocator

from parser import parse_dialogue, DialogueLine
from utils import load_config

# 無音ファイルのパス（スクリプトと同じディレクトリに配置）
SILENCE_FILE = os.path.join(os.path.dirname(__file__), "silence_2sec.mp3")
# 無音判定用のキーワード
SILENCE_KEYWORDS = ["（無音）"]
# 壊れたファイルと判定するサイズ閾値（バイト）
MIN_VALID_FILE_SIZE = 1024


def sanitize_filename(text: str, max_length: int = 200) -> str:
    """ファイル名に使えない文字を除去"""
    sanitized = re.sub(r'[\\/:*?"<>|\n\r\t]', '', text)
    sanitized = sanitized.replace(' ', '_')
    # cp932でエンコードできない文字を除去
    sanitized = sanitized.encode('cp932', errors='ignore').decode('cp932')
    if len(sanitized) > max_length:
        sanitized = sanitized[:max_length]
    return sanitized



def get_voice_id(character: str, config: dict) -> str | None:
    """キャラ名からvoice_idを取得"""
    return config.get("character_voices", {}).get(character)


def fetch_available_voices(client: ElevenLabs) -> dict:
    """ElevenLabs APIから利用可能なボイス一覧を取得"""
    try:
        response = client.voices.get_all()
        return {v.name: v.voice_id for v in response.voices}
    except Exception as e:
        print(f"警告: ボイス一覧の取得に失敗しました: {e}")
        return {}


def check_missing_voices(dialogues: list, config: dict, available_voices: dict) -> list:
    """台本内のキャラで、config.jsonにvoice_idがないものを検出し、候補を提案"""
    character_voices = config.get("character_voices", {})
    
    # 台本内のユニークなキャラ名を抽出
    script_characters = set(d.character for d in dialogues)
    
    # 不足しているキャラを検出
    missing = []
    for char in script_characters:
        if char not in character_voices:
            # ElevenLabsに同名のボイスがあるか確認
            suggested_id = available_voices.get(char)
            missing.append({
                "character": char,
                "suggested_voice_id": suggested_id,
                "count": sum(1 for d in dialogues if d.character == char)
            })
    
    return missing


def prompt_add_missing_voices(missing: list, config: dict, config_path: str = "config.json") -> bool:
    """不足しているキャラのvoice_idを追加するか確認"""
    if not missing:
        return True
    
    print("\n" + "=" * 60)
    print("不足しているキャラクターを検出しました")
    print("=" * 60)
    
    addable = [m for m in missing if m["suggested_voice_id"]]
    not_addable = [m for m in missing if not m["suggested_voice_id"]]
    
    if addable:
        print("\n[自動追加可能] ElevenLabsに同名のボイスがあります:")
        for m in addable:
            print(f"  - {m['character']} ({m['count']}件) -> voice_id: {m['suggested_voice_id']}")
    
    if not_addable:
        print("\n[手動設定が必要] ElevenLabsに同名のボイスがありません:")
        for m in not_addable:
            print(f"  - {m['character']} ({m['count']}件)")
        print("  ※ これらのキャラはスキップされます")
    
    if addable:
        print("\n自動追加可能なキャラをconfig.jsonに追加しますか？ [Y/n]: ", end="")
        confirm = input().strip().lower()
        if confirm != 'n':
            # config.jsonに追加
            for m in addable:
                config["character_voices"][m["character"]] = m["suggested_voice_id"]
            
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            
            print(f"\nconfig.jsonに{len(addable)}件のキャラを追加しました")
            return True
    
    if not_addable:
        print("\n不足キャラがありますが、続行しますか？ [y/N]: ", end="")
        confirm = input().strip().lower()
        return confirm == 'y'
    
    return True


def load_pronunciation_dict(config: dict) -> list[PronunciationDictionaryVersionLocator] | None:
    """config.json から発音辞書ロケータを読み込む"""
    pd = config.get("pronunciation_dictionary", {})
    dict_id = pd.get("id")
    version_id = pd.get("version_id")
    if dict_id and version_id:
        return [
            PronunciationDictionaryVersionLocator(
                pronunciation_dictionary_id=dict_id,
                version_id=version_id,
            )
        ]
    return None


def generate_audio(
    client: ElevenLabs,
    text: str,
    voice_id: str,
    model_id: str = "eleven_v3",
    output_format: str = "mp3_44100_128",
    language_code: str = "ja",
    previous_text: str | None = None,
    next_text: str | None = None,
    pronunciation_dictionary_locators: list[PronunciationDictionaryVersionLocator] | None = None,
) -> bytes:
    """ElevenLabs APIで音声を生成"""
    kwargs = {
        "text": text,
        "voice_id": voice_id,
        "model_id": model_id,
        "output_format": output_format,
        "language_code": language_code,
    }
    # eleven_v3ではapply_language_text_normalization非対応
    if model_id != "eleven_v3":
        kwargs["apply_language_text_normalization"] = True

    if previous_text:
        kwargs["previous_text"] = previous_text
    if next_text:
        kwargs["next_text"] = next_text
    if pronunciation_dictionary_locators:
        kwargs["pronunciation_dictionary_locators"] = pronunciation_dictionary_locators

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


def is_silence_text(text: str) -> bool:
    """セリフが無音として扱うべきかを判定"""
    for keyword in SILENCE_KEYWORDS:
        if keyword in text:
            return True
    return False


def copy_silence_file(output_filepath: str) -> bool:
    """無音ファイルを指定パスにコピー"""
    if not os.path.exists(SILENCE_FILE):
        print(f"    警告: 無音ファイルが見つかりません: {SILENCE_FILE}")
        return False
    
    shutil.copy2(SILENCE_FILE, output_filepath)
    return True


def check_and_fix_broken_file(filepath: str, dialogue_index: int) -> bool:
    """生成されたファイルが壊れていないかチェックし、壊れていれば無音ファイルで置換"""
    if not os.path.exists(filepath):
        return False
    
    file_size = os.path.getsize(filepath)
    if file_size < MIN_VALID_FILE_SIZE:
        print(f"    警告: #{dialogue_index} が{file_size}バイトです。無音ファイルで置換します")
        if os.path.exists(SILENCE_FILE):
            shutil.copy2(SILENCE_FILE, filepath)
            return True
        else:
            print(f"    エラー: 無音ファイルが見つかりません: {SILENCE_FILE}")
            return False
    return True


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

    # 発音辞書
    pd_locators = load_pronunciation_dict(config)
    if pd_locators:
        print("発音辞書を適用します")
    
    for i, dialogue in enumerate(dialogues):
        # ファイル名: 1_キャラ名_セリフ内容.mp3
        text_content = sanitize_filename(dialogue.text)
        filename = f"{dialogue.index}_{dialogue.character}_{text_content}.mp3"
        filepath = output_path / filename
        
        # 無音判定：APIを叩く前にチェック
        if is_silence_text(dialogue.text):
            print(f"[{dialogue.index:03d}] {dialogue.character} → 無音ファイル配置")
            if copy_silence_file(str(filepath)):
                print(f"    -> Saved: {filename}")
                results.append({
                    "index": dialogue.index,
                    "character": dialogue.character,
                    "status": "success",
                    "filepath": str(filepath),
                    "silence": True,
                })
            else:
                results.append({
                    "index": dialogue.index,
                    "character": dialogue.character,
                    "status": "error",
                    "reason": "無音ファイルのコピーに失敗",
                })
            continue
        
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
        
        # 前後のコンテキスト
        # 注意: eleven_v3モデルはprevious_text/next_textに非対応
        previous_text = None
        next_text = None

        if use_context and model_id != "eleven_v3":
            if i > 0:
                prev = dialogues[i - 1]
                previous_text = f"{prev.character}「{prev.text}」" if prev.character != dialogue.character else prev.text
            if i < len(dialogues) - 1:
                nxt = dialogues[i + 1]
                next_text = f"{nxt.character}「{nxt.text}」" if nxt.character != dialogue.character else nxt.text
        
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
                pronunciation_dictionary_locators=pd_locators,
            )
            
            save_audio(audio_bytes, str(filepath))
            
            # 生成後チェック：ファイルサイズが小さすぎる場合は無音ファイルで置換
            check_and_fix_broken_file(str(filepath), dialogue.index)
            
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
    
    # 不足キャラのチェック
    print("ボイス設定を確認中...")
    available_voices = fetch_available_voices(client)
    missing = check_missing_voices(dialogues, config, available_voices)
    
    if missing:
        if not prompt_add_missing_voices(missing, config):
            print("Cancelled.")
            sys.exit(0)
        # configを再読み込み（追加された場合）
        config = load_config()
    
    print(f"\n{len(dialogues)} 件のセリフを検出しました:\n")
    for d in dialogues:
        voice_id = get_voice_id(d.character, config)
        status = "OK" if voice_id else "NG (voice_id未設定)"
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


def main_from_file(filepath: str, auto_confirm: bool = False, output_name: str = None):
    """ファイルから台本を読み込んで処理
    
    Args:
        filepath: 台本ファイルのパス
        auto_confirm: 確認をスキップするか
        output_name: 出力フォルダ名（台本タイトル）。指定するとoutput/{output_name}/に出力
    """
    load_dotenv()
    
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        print("Error: ELEVENLABS_API_KEY not found in environment variables")
        sys.exit(1)
    
    config = load_config()
    client = ElevenLabs(api_key=api_key)
    
    print("=" * 60)
    print("ElevenLabs TTS Generator")
    print("=" * 60)
    
    with open(filepath, 'r', encoding='utf-8') as f:
        input_text = f.read()
    
    print(f"\nファイル読み込み: {filepath}\n")
    
    dialogues = parse_dialogue(input_text)
    
    if not dialogues:
        print("Error: No dialogues found in input")
        sys.exit(1)
    
    # 不足キャラのチェック
    print("ボイス設定を確認中...")
    available_voices = fetch_available_voices(client)
    missing = check_missing_voices(dialogues, config, available_voices)
    
    if missing and not auto_confirm:
        if not prompt_add_missing_voices(missing, config):
            print("Cancelled.")
            sys.exit(0)
        # configを再読み込み（追加された場合）
        config = load_config()
    elif missing and auto_confirm:
        # 自動確認モードでも追加可能なものは追加
        addable = [m for m in missing if m["suggested_voice_id"]]
        if addable:
            for m in addable:
                config["character_voices"][m["character"]] = m["suggested_voice_id"]
            with open("config.json", 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=4)
            print(f"\nconfig.jsonに{len(addable)}件のキャラを自動追加しました")
    
    print(f"\n{len(dialogues)} 件のセリフを検出しました:\n")
    for d in dialogues:
        voice_id = get_voice_id(d.character, config)
        status = "OK" if voice_id else "NG (voice_id未設定)"
        print(f"  {d.index:03d}. [{d.character}] {status}")
    
    # 出力先の決定
    base_output_dir = config.get("output_directory", "./output/")
    if output_name:
        output_dir = os.path.join(base_output_dir, output_name)
    else:
        output_dir = base_output_dir
    
    print(f"\n出力先: {output_dir}")
    
    if not auto_confirm:
        print("\n生成を開始しますか？ [y/N]: ", end="")
        confirm = input().strip().lower()
        if confirm != 'y':
            print("Cancelled.")
            sys.exit(0)
    
    print("\n" + "-" * 60)
    print("音声生成を開始します...")
    print("-" * 60 + "\n")
    
    results = process_dialogues(dialogues, config, client, output_dir)
    
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
    print(f"\n出力先: {output_dir}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="ElevenLabs TTS Generator")
    parser.add_argument("-f", "--file", help="台本ファイルのパス")
    parser.add_argument("-o", "--output", help="出力フォルダ名（台本タイトル）")
    parser.add_argument("-y", "--yes", action="store_true", help="確認をスキップ")
    parser.add_argument("--list-voices", action="store_true", help="登録済みボイス一覧を表示")
    
    args = parser.parse_args()
    
    if args.list_voices:
        list_voices()
    elif args.file:
        main_from_file(args.file, args.yes, args.output)
    else:
        main(auto_confirm=args.yes)
