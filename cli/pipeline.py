#!/usr/bin/env python3
"""
ボイス生成パイプライン（CLI）
_split.csv + _elevenlabs.csv → 整合性チェック → ボイス生成 → MP3チェック → YMM4生成

Claude Code から呼び出して使う:
  python pipeline.py --split xxx_split.csv --elevenlabs xxx_elevenlabs.csv
"""
import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

# プロジェクトルートをパスに追加（cli/ の1つ上）
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.config import load_config
from core.csv_io import read_csv_rows, check_csv_alignment
from core.client import get_client
from core.generator import (
    get_voice_id,
    generate_audio,
    save_audio,
    sanitize_filename,
    is_silence_text,
    copy_silence_file,
    check_and_fix_broken_file,
    fetch_available_voices,
    load_pronunciation_dict,
)
from core.parser import DialogueLine

# ymm4-tools のモジュールをインポート
YMMP4_TOOLS_DIR = os.path.join(os.path.dirname(PROJECT_ROOT), 'ymm4-tools')
if not os.path.exists(YMMP4_TOOLS_DIR):
    YMMP4_TOOLS_DIR = os.path.join(PROJECT_ROOT, '..', 'ymm4-tools')
sys.path.insert(0, YMMP4_TOOLS_DIR)
from ymm4_generate import generate_ymmp, verify_telop_vs_csv, print_telop_verification


# ══════════════════════════════════════════════════════════════════════════════
# 1. 整合性チェック
# ══════════════════════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════════════════════
# 2. ボイス生成
# ══════════════════════════════════════════════════════════════════════════════

def parse_elevenlabs_csv(filepath: str) -> list[DialogueLine]:
    """_elevenlabs.csv を DialogueLine リストに変換"""
    dialogues = []
    with open(filepath, 'r', encoding='utf-8-sig', newline='') as f:
        reader = csv.reader(f)
        next(reader, None)  # ヘッダースキップ
        for row in reader:
            if len(row) < 3:
                continue
            try:
                serial = int(row[0])
            except ValueError:
                continue
            text = row[2].strip()
            char_count = int(row[3]) if len(row) > 3 and row[3].strip().isdigit() else len(text)
            dialogues.append(DialogueLine(
                index=serial,
                character=row[1].strip(),
                text=text,
                char_count=char_count,
            ))
    return dialogues


def generate_voices(
    dialogues: list[DialogueLine],
    config: dict,
    client: ElevenLabs,
    output_dir: str,
    delay: float = 0.5,
) -> list[dict]:
    """ボイスを生成し、結果リストを返す"""
    results = []
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    model_id = config.get("default_model", "eleven_v3")
    output_format = config.get("default_output_format", "mp3_44100_128")
    language_code = config.get("language_code", "ja")

    # 発音辞書
    pd_locators = load_pronunciation_dict(config)
    if pd_locators:
        print("  発音辞書を適用します")

    for i, d in enumerate(dialogues):
        text_content = sanitize_filename(d.text)
        filename = f"{d.index}_{d.character}_{text_content}.mp3"
        filepath = output_path / filename

        # 無音判定
        if is_silence_text(d.text):
            print(f"[{d.index:03d}] {d.character} → 無音ファイル配置")
            if copy_silence_file(str(filepath)):
                results.append({"index": d.index, "character": d.character,
                                "status": "success", "filepath": str(filepath), "silence": True})
            else:
                results.append({"index": d.index, "character": d.character,
                                "status": "error", "reason": "無音ファイルのコピーに失敗"})
            continue

        voice_id = get_voice_id(d.character, config)
        if not voice_id:
            print(f"[SKIP] voice_id未設定: {d.character}")
            results.append({"index": d.index, "character": d.character,
                            "status": "skipped", "reason": "voice_id未設定"})
            continue

        try:
            print(f"[{d.index:03d}] {d.character} ({d.char_count}字)...")
            audio_bytes = generate_audio(
                client=client,
                text=d.text,
                voice_id=voice_id,
                model_id=model_id,
                output_format=output_format,
                language_code=language_code,
                pronunciation_dictionary_locators=pd_locators,
            )
            save_audio(audio_bytes, str(filepath))
            check_and_fix_broken_file(str(filepath), d.index)
            print(f"    -> {filename}")
            results.append({"index": d.index, "character": d.character,
                            "status": "success", "filepath": str(filepath)})

            if i < len(dialogues) - 1:
                time.sleep(delay)

        except Exception as e:
            print(f"[ERROR] {d.character}: {e}")
            results.append({"index": d.index, "character": d.character,
                            "status": "error", "reason": str(e)})

    return results


# ══════════════════════════════════════════════════════════════════════════════
# 3. MP3 vs 台本 整合性チェック
# ══════════════════════════════════════════════════════════════════════════════

def check_mp3_alignment(elevenlabs_path: str, output_dir: str) -> tuple[bool, list[str]]:
    """生成されたMP3ファイルと _elevenlabs.csv の整合性チェック"""
    el_rows = read_csv_rows(elevenlabs_path)
    mp3_files = sorted(Path(output_dir).glob("*.mp3"))

    messages = []
    messages.append(f"台本行数: {len(el_rows)}")
    messages.append(f"MP3ファイル数: {len(mp3_files)}")

    if len(el_rows) != len(mp3_files):
        messages.append(f"⚠ 数が一致しません（差: {abs(len(el_rows) - len(mp3_files))}）")

    # MP3から連番を抽出してマッピング
    mp3_map = {}
    for fp in mp3_files:
        parts = fp.stem.split('_', 2)
        if len(parts) >= 2:
            try:
                serial = int(parts[0])
                char = parts[1]
                mp3_map[serial] = char
            except ValueError:
                pass

    # 台本の各行にMP3が存在するか確認
    missing = []
    char_mismatch = []
    for row in el_rows:
        serial = row['serial']
        if serial not in mp3_map:
            missing.append(f"  連番{serial}: {row['character']} — MP3なし")
        elif mp3_map[serial] != row['character']:
            char_mismatch.append(
                f"  連番{serial}: 台本={row['character']} / MP3={mp3_map[serial]}")

    if missing:
        messages.append(f"⚠ {len(missing)}件のMP3が欠落:")
        messages.extend(missing[:10])
        if len(missing) > 10:
            messages.append(f"  ...他 {len(missing) - 10}件")

    if char_mismatch:
        messages.append(f"⚠ {len(char_mismatch)}件のキャラ名不一致:")
        messages.extend(char_mismatch[:10])

    if not missing and not char_mismatch:
        messages.append("✓ MP3整合性OK: 全行にMP3が存在、キャラ名一致")

    ok = len(missing) == 0
    return ok, messages


# ══════════════════════════════════════════════════════════════════════════════
# 4. YMM4生成
# ══════════════════════════════════════════════════════════════════════════════

def find_original_csv(split_csv_path: str) -> str | None:
    """_split.csv と同じ台本フォルダから元台本CSVを探す

    元台本CSV = 台本フォルダ内の _split / _elevenlabs がつかないCSVファイル
    """
    script_dir = os.path.dirname(split_csv_path)
    for f in sorted(Path(script_dir).glob("*.csv")):
        name = f.name
        if '_split' in name or '_elevenlabs' in name:
            continue
        return str(f)
    return None


def generate_ymm4(
    audio_dir: str,
    split_csv_path: str,
    project_name: str,
    config: dict,
    original_csv_path: str = None,
    elevenlabs_csv_path: str = None,
) -> str:
    """YMM4 ymmpファイルを生成し、出力パスを返す"""
    ymm4_config = config.get('ymm4', {})

    template_path = ymm4_config.get('template_path')
    if not template_path:
        raise ValueError("config.json に ymm4.template_path が未設定です")

    voice_base_dir_win = ymm4_config.get('voice_base_dir_win')
    if not voice_base_dir_win:
        raise ValueError("config.json に ymm4.voice_base_dir_win が未設定です")

    # voice_base_dir_win にプロジェクト名を追加してボイスフォルダパスを構築
    voice_dir_win = voice_base_dir_win.rstrip('\\') + '\\' + project_name + '\\ボイス'

    gap_seconds = ymm4_config.get('gap_seconds', 0.3)
    default_volume = ymm4_config.get('default_volume', 50.0)
    voice_layer = ymm4_config.get('voice_layer', 15)
    character_mapping = ymm4_config.get('character_mapping', {})

    # 出力先はボイスフォルダの親フォルダ（プロジェクトフォルダ）
    project_dir = str(Path(audio_dir).parent)
    output_path = os.path.join(project_dir, f"{project_name}.ymmp")

    result = generate_ymmp(
        template_path=template_path,
        audio_dir=audio_dir,
        output_path=output_path,
        voice_base_dir_win=voice_dir_win,
        gap_seconds=gap_seconds,
        default_volume=default_volume,
        enable_tachie=True,
        character_mapping=character_mapping,
        script_csv_path=split_csv_path,
        narration_csv_path=split_csv_path,
        voice_layer=voice_layer,
    )

    if not result.success:
        raise RuntimeError(f"YMM4生成失敗: {result.error_message}")

    return output_path


def check_tachie_paths(ymmp_path: str, check_type: str = "テンプレート") -> list:
    """ymmpファイル内の立ち絵パスが実際に存在するかチェック

    Args:
        ymmp_path: ymmpファイルのパス
        check_type: 表示用ラベル（"テンプレート" or "生成ymmp"）

    Returns:
        不正パスのリスト [(キャラ名, フィールド名, パス), ...]
    """
    with open(ymmp_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    issues = []
    for c in data.get('Characters', []):
        name = c.get('Name', '')
        char_param = c.get('TachieCharacterParameter') or {}
        item_param = c.get('TachieDefaultItemParameter') or {}

        directory = char_param.get('Directory', '')
        default_face = item_param.get('DefaultFace', '')

        if directory and not os.path.exists(directory):
            issues.append((name, 'Directory', directory))
        if default_face and not os.path.exists(default_face):
            issues.append((name, 'DefaultFace', default_face))

    return issues


def print_tachie_check(issues: list, check_type: str = "テンプレート"):
    """立ち絵パスチェック結果を表示"""
    if not issues:
        print(f"  ✓ {check_type}の立ち絵パス: 全て正常")
    else:
        print(f"  ⚠ {check_type}の立ち絵パスに問題あり: {len(issues)}件")
        for name, field, path in issues:
            print(f"    ✗ {name} ({field}): {path}")


# ══════════════════════════════════════════════════════════════════════════════
# メイン パイプライン
# ══════════════════════════════════════════════════════════════════════════════

def run_pipeline(
    split_csv: str,
    elevenlabs_csv: str,
    force: bool = False,
    skip_voice: bool = False,
    skip_ymm4: bool = False,
):
    """パイプライン全体を実行"""

    # ── 準備 ──
    base_dir = os.path.dirname(__file__)

    if not skip_voice:
        try:
            client = get_client()
        except RuntimeError as e:
            print(f"ERROR: {e}")
            sys.exit(1)

    config = load_config(os.path.join(base_dir, 'config.json'))

    # プロジェクト名を _split.csv のファイル名から推定
    stem = Path(split_csv).stem
    project_name = stem.removesuffix('_split')
    # 「 - 台本」等のサフィックスを除去
    for suffix in [' - 台本', '- 台本', '_台本', ' 台本']:
        project_name = project_name.removesuffix(suffix)

    # 出力フォルダの決定
    voice_base_dir = config.get('ymm4', {}).get(
        'voice_base_dir_win', os.path.join(base_dir, 'output'))
    project_dir = os.path.join(voice_base_dir, project_name)
    voice_output_dir = os.path.join(project_dir, 'ボイス')

    print("=" * 60)
    print(f"パイプライン実行: {project_name}")
    print("=" * 60)
    print(f"  split CSV:      {split_csv}")
    print(f"  elevenlabs CSV: {elevenlabs_csv}")
    print(f"  出力先:         {voice_output_dir}")
    print()

    # ── STEP 1: 整合性チェック (_split vs _elevenlabs) ──
    print("─" * 40)
    print("STEP 1: 整合性チェック（台本 vs ボイスCSV）")
    print("─" * 40)
    ok, messages = check_csv_alignment(split_csv, elevenlabs_csv)
    for msg in messages:
        print(f"  {msg}")
    print()

    if not ok and not force:
        print("ERROR: 整合性チェックに失敗しました。--force で強制続行できます。")
        sys.exit(1)

    if skip_voice:
        print("(--skip-voice: ボイス生成をスキップ)")
    else:
        # ── STEP 2: ボイス生成 ──
        print("─" * 40)
        print("STEP 2: ボイス生成")
        print("─" * 40)

        dialogues = parse_elevenlabs_csv(elevenlabs_csv)
        print(f"  {len(dialogues)}件のセリフを処理します")

        # voice_id 未設定キャラのチェック
        missing_voices = set()
        for d in dialogues:
            if not get_voice_id(d.character, config):
                missing_voices.add(d.character)
        if missing_voices:
            print(f"\n  ⚠ voice_id 未設定: {', '.join(sorted(missing_voices))}")
            # ElevenLabsに同名ボイスがあれば自動追加
            available = fetch_available_voices(client)
            added = []
            for char in missing_voices:
                vid = available.get(char)
                if vid:
                    config["character_voices"][char] = vid
                    added.append(char)
            if added:
                config_path = os.path.join(base_dir, 'config.json')
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(config, f, ensure_ascii=False, indent=4)
                print(f"  → {len(added)}件を自動追加: {', '.join(added)}")

        print()
        results = generate_voices(dialogues, config, client, voice_output_dir)

        success = sum(1 for r in results if r["status"] == "success")
        skipped = sum(1 for r in results if r["status"] == "skipped")
        errors = sum(1 for r in results if r["status"] == "error")
        print(f"\n  成功: {success} / スキップ: {skipped} / エラー: {errors}")
        print()

        if errors > 0:
            print("  エラー詳細:")
            for r in results:
                if r["status"] == "error":
                    print(f"    - #{r['index']} {r['character']}: {r['reason']}")
            print()

    # ── STEP 3: MP3整合性チェック ──
    print("─" * 40)
    print("STEP 3: MP3整合性チェック")
    print("─" * 40)
    ok, messages = check_mp3_alignment(elevenlabs_csv, voice_output_dir)
    for msg in messages:
        print(f"  {msg}")
    print()

    if not ok:
        print("⚠ MP3の欠落がありますが、YMM4生成は続行します。")
        print()

    if skip_ymm4:
        print("(--skip-ymm4: YMM4生成をスキップ)")
    else:
        # ── STEP 3.5: テンプレート立ち絵パスチェック ──
        ymm4_config = config.get('ymm4', {})
        template_path = ymm4_config.get('template_path', '')
        if template_path and os.path.exists(template_path):
            tpl_issues = check_tachie_paths(template_path, "テンプレート")
            print_tachie_check(tpl_issues, "テンプレート")
            print()

        # ── STEP 4: YMM4生成 ──
        print("─" * 40)
        print("STEP 4: YMM4生成")
        print("─" * 40)

        # 元台本CSVを自動検出（霊夢/魔理沙AquesTalk混在対応）
        original_csv = find_original_csv(split_csv)
        if original_csv:
            print(f"  元台本CSV検出: {os.path.basename(original_csv)}")
        else:
            print("  元台本CSV: なし（ElevenLabsのみモード）")

        try:
            ymmp_path = generate_ymm4(
                audio_dir=voice_output_dir,
                split_csv_path=split_csv,
                project_name=project_name,
                config=config,
                original_csv_path=original_csv,
                elevenlabs_csv_path=elevenlabs_csv,
            )
            print(f"\n  ✓ 生成完了: {ymmp_path}")
        except Exception as e:
            print(f"\n  ERROR: {e}")
            sys.exit(1)

        # ── STEP 5: テロップ検証 ──
        print("─" * 40)
        print("STEP 5: テロップ検証（ymmp vs CSV）")
        print("─" * 40)
        mismatches = verify_telop_vs_csv(ymmp_path, split_csv)
        # VoiceItem数を取得
        with open(ymmp_path, 'r', encoding='utf-8-sig') as f:
            ymmp_data = json.load(f)
        voice_count = sum(
            1 for item in ymmp_data['Timelines'][0]['Items']
            if item.get('$type', '').startswith('YukkuriMovieMaker.Project.Items.VoiceItem')
        )
        print_telop_verification(mismatches, voice_count)
        print()

        # ── STEP 5.5: 生成ymmp立ち絵パスチェック ──
        ymmp_issues = check_tachie_paths(ymmp_path, "生成ymmp")
        print_tachie_check(ymmp_issues, "生成ymmp")
        print()

    # ── STEP 6: 音声長チェック ──
    print("─" * 40)
    print("STEP 6: 音声長チェック")
    print("─" * 40)
    try:
        from verify_voice import check_durations
        anomalies = check_durations(elevenlabs_csv, voice_output_dir, verbose=True)
        if anomalies:
            print(f"\n  ⚠ {len(anomalies)}件の異常な長さのファイルがあります。確認してください。")
    except ImportError:
        print("  verify_voice.py が見つかりません。スキップ。")
    print()

    # ── STEP 7: 最終ボイス文字起こし検証 ──
    if not skip_ymm4:
        print("─" * 40)
        print("STEP 7: 最終ボイス文字起こし検証")
        print("─" * 40)
        try:
            import speech_recognition as sr_mod
            from pydub import AudioSegment as AS
            import tempfile, re as re_mod

            with open(ymmp_path, 'r', encoding='utf-8-sig') as f:
                ymmp_data_verify = json.load(f)
            v_items = [i for i in ymmp_data_verify['Timelines'][0]['Items']
                       if 'VoiceItem' in i.get('$type', '') and i.get('Hatsuon', '')]
            if v_items:
                last_v = max(v_items, key=lambda x: x.get('Frame', 0))
                last_serif = last_v.get('Serif', '')
                last_hatsuon = last_v.get('Hatsuon', '')
                last_char = last_v.get('CharacterName', '')

                recognizer = sr_mod.Recognizer()
                tmp_wav = os.path.join(tempfile.gettempdir(), 'pipeline_verify_last.wav')
                audio_seg = AS.from_mp3(last_hatsuon)
                audio_seg.export(tmp_wav, format="wav")
                with sr_mod.AudioFile(tmp_wav) as source:
                    audio_data = recognizer.record(source)
                try:
                    transcript = recognizer.recognize_google(audio_data, language="ja-JP")
                except Exception:
                    transcript = "(認識不能)"

                clean_serif = re_mod.sub(r'\[.*?\]', '', last_serif).strip()
                match_chars = sum(1 for c in clean_serif if c in transcript)
                ratio = match_chars / max(len(clean_serif), 1)
                mark = "✓" if ratio > 0.3 else "✗ ズレの可能性あり"

                print(f"  最終ボイス: [{last_char}] {clean_serif[:40]}")
                print(f"  文字起こし: {transcript[:40]}")
                print(f"  一致率: {ratio:.0%} {mark}")
                if os.path.exists(tmp_wav):
                    os.remove(tmp_wav)
            else:
                print("  ボイスアイテムなし")
        except ImportError:
            print("  SpeechRecognition/pydub 未インストール。スキップ。")
        except Exception as e:
            print(f"  検証エラー: {e}")
        print()

    # ── 完了 ──
    print()
    print("=" * 60)
    print("パイプライン完了")
    print("=" * 60)
    print(f"  プロジェクト: {project_name}")
    print(f"  ボイス:       {voice_output_dir}")
    if not skip_ymm4:
        print(f"  ymmp:         {ymmp_path}")


def main():
    parser = argparse.ArgumentParser(
        description='ボイス生成パイプライン: 整合性チェック → ボイス生成 → MP3チェック → YMM4生成',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python pipeline.py --split 台本_split.csv --elevenlabs 台本_elevenlabs.csv
  python pipeline.py --split 台本_split.csv --elevenlabs 台本_elevenlabs.csv --skip-voice
  python pipeline.py --split 台本_split.csv --elevenlabs 台本_elevenlabs.csv --force
        """
    )
    parser.add_argument('--split', '-s', required=True,
                        help='_split.csv のパス')
    parser.add_argument('--elevenlabs', '-e', required=True,
                        help='_elevenlabs.csv のパス')
    parser.add_argument('--force', '-f', action='store_true',
                        help='整合性チェック失敗時も続行')
    parser.add_argument('--skip-voice', action='store_true',
                        help='ボイス生成をスキップ（既にMP3がある場合）')
    parser.add_argument('--skip-ymm4', action='store_true',
                        help='YMM4生成をスキップ')
    args = parser.parse_args()

    run_pipeline(
        split_csv=args.split,
        elevenlabs_csv=args.elevenlabs,
        force=args.force,
        skip_voice=args.skip_voice,
        skip_ymm4=args.skip_ymm4,
    )


if __name__ == '__main__':
    main()
