"""ボイス読み上げ検証ツール

生成済みMP3の品質を検証する。
1. 音声長チェック: 文字数に対して異常に長い音声を検出（全件・高速）
2. 文字起こし検証: Google Speech APIで台本との一致を確認（オプション）

使い方:
    python verify_voice.py <elevenlabs_csv> <voice_dir> [--sample N] [--duration-only]

    --sample N: 文字起こし検証をランダムN件のみ（省略時は全件）
    --duration-only: 音声長チェックのみ実行（文字起こしスキップ）
"""

import sys
import csv
import os
import re
import argparse
import random
import tempfile

try:
    from pydub import AudioSegment
except ImportError:
    print("ERROR: pip install pydub が必要です")
    sys.exit(1)

try:
    import speech_recognition as sr
    HAS_SR = True
except ImportError:
    HAS_SR = False


def clean_serif(text):
    """タグ・カッコを除去して比較用テキストを作る"""
    s = re.sub(r'\[.*?\]', '', text).strip()
    s = s.replace('（', '').replace('）', '')
    s = s.replace('(', '').replace(')', '')
    return s


def transcribe_mp3(recognizer, mp3_path, tmp_wav):
    """MP3を文字起こし"""
    audio = AudioSegment.from_mp3(mp3_path)
    audio.export(tmp_wav, format="wav")

    with sr.AudioFile(tmp_wav) as source:
        audio_data = recognizer.record(source)

    try:
        return recognizer.recognize_google(audio_data, language="ja-JP")
    except sr.UnknownValueError:
        return ""
    except sr.RequestError as e:
        return f"(API_ERROR: {e})"


def calc_similarity(expected, actual):
    """文字単位の一致率"""
    if not expected:
        return 1.0 if not actual else 0.0
    match_chars = sum(1 for c in expected if c in actual)
    return match_chars / len(expected)


def trim_trailing_silence(
    voice_dir: str,
    silence_thresh: int = -45,
    min_trailing_ms: int = 500,
    keep_ms: int = 100,
    verbose: bool = True,
) -> list[tuple[str, int, int]]:
    """末尾無音をトリミング

    Args:
        voice_dir: MP3フォルダ
        silence_thresh: 無音判定の閾値(dBFS)
        min_trailing_ms: この長さ以上の末尾無音をトリミング対象とする
        keep_ms: トリミング後に残す余白(ms)
        verbose: 進捗表示

    Returns:
        トリミングしたファイルのリスト [(filename, old_dur, new_dur), ...]
    """
    from pydub.silence import detect_nonsilent

    mp3s = sorted(f for f in os.listdir(voice_dir) if f.endswith('.mp3') and '_pretrim' not in f)
    trimmed = []

    for fname in mp3s:
        fpath = os.path.join(voice_dir, fname)
        try:
            audio = AudioSegment.from_mp3(fpath)
        except Exception:
            continue

        dur = len(audio)
        nonsilent = detect_nonsilent(audio, min_silence_len=100, silence_thresh=silence_thresh, seek_step=10)

        if not nonsilent:
            continue

        trailing = dur - nonsilent[-1][1]
        if trailing < min_trailing_ms:
            continue

        end_pos = min(nonsilent[-1][1] + keep_ms, dur)
        trimmed_audio = audio[:end_pos]
        trimmed_audio.export(fpath, format='mp3', bitrate='192k')
        trimmed.append((fname, dur, len(trimmed_audio)))

    if verbose:
        print(f"\n{'='*60}")
        print(f"末尾無音トリミング（全{len(mp3s)}件スキャン）")
        print(f"{'='*60}")
        print(f"  閾値: {silence_thresh}dBFS, 対象: {min_trailing_ms}ms以上, 残す余白: {keep_ms}ms")
        if trimmed:
            total_saved = sum(old - new for _, old, new in trimmed)
            print(f"  トリミング: {len(trimmed)}件, 合計短縮: {total_saved}ms ({total_saved/1000:.1f}秒)")
            for fname, old, new in sorted(trimmed, key=lambda x: x[1] - x[2], reverse=True)[:10]:
                print(f"    {old - new:5d}ms短縮 | {old:5d} -> {new:5d}ms | {fname[:60]}")
            if len(trimmed) > 10:
                print(f"    ... 他{len(trimmed) - 10}件")
        else:
            print("  対象なし OK")

    return trimmed


def check_durations(csv_path, voice_dir, verbose=True):
    """音声長チェック: 文字数に対して異常に長いファイルを検出"""
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader)
        csv_rows = {}
        for r in reader:
            clean = clean_serif(r[2])
            csv_rows[r[0]] = (r[1], clean, len(clean))

    mp3s = [f for f in os.listdir(voice_dir) if f.endswith('.mp3')]
    anomalies = []

    for fname in mp3s:
        serial = fname.split('_')[0]
        fpath = os.path.join(voice_dir, fname)
        try:
            a = AudioSegment.from_mp3(fpath)
            dur = len(a) / 1000
        except Exception:
            continue

        char, text, tlen = csv_rows.get(serial, ('?', '?', 0))

        # 日本語は約5-8文字/秒。上限 = 文字数×0.5秒+3秒、最低8秒
        expected_max = max(tlen * 0.5 + 3, 8)
        if dur > expected_max and dur > 15:
            anomalies.append((serial, char, dur, tlen, text[:40], fname))

    if verbose:
        print(f"\n{'='*60}")
        print(f"音声長チェック（全{len(mp3s)}件）")
        print(f"{'='*60}")
        if anomalies:
            for serial, char, dur, tlen, text, fname in sorted(anomalies, key=lambda x: -x[2]):
                print(f"  ★ #{serial} [{char}] {dur:.1f}秒 (文字数{tlen}) {text}")
            print(f"\n異常: {len(anomalies)}件")
        else:
            print("  異常なし ✓")

    return anomalies


def verify_voices(csv_path, voice_dir, sample_n=None, verbose=True, duration_only=False):
    """メイン検証処理"""
    # 1. 音声長チェック（常に全件実行）
    anomalies = check_durations(csv_path, voice_dir, verbose=verbose)

    if duration_only:
        return {'duration_anomalies': anomalies}

    if not HAS_SR:
        print("WARNING: SpeechRecognition未インストール。文字起こし検証スキップ。")
        return {'duration_anomalies': anomalies}

    # 2. 文字起こし検証
    # CSV読み込み
    with open(csv_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader)
        csv_rows = {r[0]: (r[1], r[2]) for r in reader}

    # MP3一覧
    mp3s = [f for f in os.listdir(voice_dir) if f.endswith('.mp3')]

    # テスト対象（無音・短すぎるセリフを除外）
    candidates = []
    for mp3 in mp3s:
        serial = mp3.split('_')[0]
        char, serif = csv_rows.get(serial, ('', ''))
        clean = clean_serif(serif)
        if serif and serif != '（無音）' and len(clean) > 2:
            candidates.append((mp3, serial, char, serif))

    # サンプリング
    if sample_n and sample_n < len(candidates):
        random.seed(42)
        targets = random.sample(candidates, sample_n)
    else:
        targets = candidates

    recognizer = sr.Recognizer()
    tmp_wav = os.path.join(tempfile.gettempdir(), 'verify_voice_tmp.wav')

    results = {'ok': 0, 'warn': 0, 'fail': 0, 'api_error': 0}
    failures = []

    if verbose:
        print(f"\n{'='*60}")
        print(f"ボイス読み上げ検証")
        print(f"{'='*60}")
        print(f"  対象: {len(targets)}件 (全{len(candidates)}件中)")
        print(f"  CSV:  {csv_path}")
        print(f"  音声: {voice_dir}")
        print()

    for i, (mp3, serial, csv_char, csv_serif) in enumerate(
            sorted(targets, key=lambda x: int(x[1]))):
        filepath = os.path.join(voice_dir, mp3)
        clean = clean_serif(csv_serif)

        transcript = transcribe_mp3(recognizer, filepath, tmp_wav)

        if transcript.startswith("(API_ERROR"):
            results['api_error'] += 1
            if verbose:
                print(f"  #{serial} [{csv_char}] API_ERROR")
            continue

        ratio = calc_similarity(clean, transcript)

        if ratio >= 0.5:
            mark = "○"
            results['ok'] += 1
        elif ratio >= 0.2:
            mark = "△"
            results['warn'] += 1
        else:
            mark = "✗"
            results['fail'] += 1
            failures.append((serial, csv_char, clean, transcript, ratio))

        if verbose and (mark != "○" or (i + 1) % 50 == 0):
            print(f"  #{serial} [{csv_char}] {mark} ({ratio:.0%}) 台本:{clean[:30]} 認識:{transcript[:30]}")

        # Progress
        if verbose and (i + 1) % 100 == 0:
            print(f"  ... {i+1}/{len(targets)} 完了")

    # Cleanup
    if os.path.exists(tmp_wav):
        os.remove(tmp_wav)

    # Summary
    total = results['ok'] + results['warn'] + results['fail']
    if verbose:
        print(f"\n{'─'*40}")
        print(f"結果: ○{results['ok']} △{results['warn']} ✗{results['fail']} (API_ERROR:{results['api_error']})")
        print(f"一致率50%以上: {results['ok']}/{total} ({results['ok']/max(total,1):.1%})")

        if failures:
            print(f"\n✗ 不一致リスト:")
            for serial, char, expected, actual, ratio in failures:
                print(f"  #{serial} [{char}] ({ratio:.0%})")
                print(f"    台本: {expected[:50]}")
                print(f"    認識: {actual[:50]}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ボイス読み上げ検証")
    parser.add_argument("csv", help="elevenlabs CSV path")
    parser.add_argument("voice_dir", help="voice MP3 directory")
    parser.add_argument("--sample", type=int, default=None, help="文字起こし検証をランダムN件のみ")
    parser.add_argument("--duration-only", action="store_true", help="音声長チェックのみ（文字起こしスキップ）")
    args = parser.parse_args()

    verify_voices(args.csv, args.voice_dir, sample_n=args.sample, duration_only=args.duration_only)
