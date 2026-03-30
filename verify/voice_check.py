#!/usr/bin/env python3
"""
ボイス文字起こしチェックツール
生成済みボイスフォルダのMP3を文字起こしして、ファイル名のテキストと比較する。
パイプラインとは独立して使う。

使い方:
  python voice_check.py <ボイスフォルダパス>
  python voice_check.py <ボイスフォルダパス> --csv  # CSV出力
"""
import argparse
import os
import re
import subprocess
import sys
import tempfile

import speech_recognition as sr

FFMPEG_PATH = "D:/YukkuriMovieMaker4/user/resources/ffmpeg/ffmpeg.exe"


def mp3_to_wav(mp3_path: str) -> str:
    """MP3をWAVに変換して一時ファイルパスを返す"""
    wav_fd, wav_path = tempfile.mkstemp(suffix=".wav")
    os.close(wav_fd)
    subprocess.run(
        [FFMPEG_PATH, "-i", mp3_path, "-y", wav_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return wav_path


def transcribe(wav_path: str) -> str:
    """WAVファイルをGoogle Speech APIで文字起こし"""
    recognizer = sr.Recognizer()
    with sr.AudioFile(wav_path) as source:
        audio_data = recognizer.record(source)
    try:
        return recognizer.recognize_google(audio_data, language="ja-JP")
    except sr.UnknownValueError:
        return "(認識不可)"
    except sr.RequestError as e:
        return f"(APIエラー: {e})"


def extract_text_from_filename(filename: str) -> str:
    """ファイル名からテキスト部分を抽出
    形式: 連番_キャラ名_テキスト.mp3 または キャラ名_テキスト.mp3
    """
    name = os.path.splitext(filename)[0]
    parts = name.split("_", 2)
    if len(parts) >= 3 and parts[0].isdigit():
        return parts[2]  # 連番_キャラ名_テキスト
    elif len(parts) >= 2:
        return parts[1]  # キャラ名_テキスト
    return name


def extract_char_from_filename(filename: str) -> str:
    """ファイル名からキャラ名を抽出"""
    name = os.path.splitext(filename)[0]
    parts = name.split("_", 2)
    if len(parts) >= 3 and parts[0].isdigit():
        return parts[1]
    elif len(parts) >= 2:
        return parts[0]
    return ""


def main():
    parser = argparse.ArgumentParser(description="ボイス文字起こしチェック")
    parser.add_argument("folder", help="ボイスフォルダのパス")
    parser.add_argument("--csv", action="store_true", help="CSV形式で出力")
    args = parser.parse_args()

    folder = args.folder
    if not os.path.isdir(folder):
        print(f"エラー: フォルダが見つかりません: {folder}")
        sys.exit(1)

    mp3_files = sorted([f for f in os.listdir(folder) if f.lower().endswith(".mp3")])

    if not mp3_files:
        print("MP3ファイルが見つかりません")
        sys.exit(1)

    print(f"チェック対象: {len(mp3_files)} ファイル\n")

    if args.csv:
        print("ファイル名,キャラ,期待テキスト,文字起こし結果")

    for i, filename in enumerate(mp3_files):
        mp3_path = os.path.join(folder, filename)
        expected = extract_text_from_filename(filename)
        character = extract_char_from_filename(filename)

        wav_path = mp3_to_wav(mp3_path)
        try:
            result = transcribe(wav_path)
        finally:
            os.unlink(wav_path)

        if args.csv:
            # CSV出力
            safe = lambda s: f'"{s}"' if "," in s else s
            print(f"{safe(filename)},{character},{safe(expected)},{safe(result)}")
        else:
            print(f"[{i+1:03d}/{len(mp3_files)}] {character}")
            print(f"  期待: {expected}")
            print(f"  結果: {result}")
            print()


if __name__ == "__main__":
    main()
