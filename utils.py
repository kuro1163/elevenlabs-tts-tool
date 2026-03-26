#!/usr/bin/env python3
"""
共通ユーティリティ関数
config.json 読み書き、ElevenLabs クライアント初期化、CSV読込・整合性チェック
"""
import csv
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_config(config_path: str = None) -> dict:
    """config.json を読み込む。config_path 省略時はスクリプトと同ディレクトリの config.json。
    ファイル不在時は空 dict を返す。"""
    if config_path is None:
        config_path = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict, config_path: str = None):
    """config.json を保存する。ensure_ascii=False, indent=4。"""
    if config_path is None:
        config_path = os.path.join(BASE_DIR, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def get_client():
    """dotenv 読込 + ElevenLabs クライアント初期化。APIキーなしは RuntimeError。"""
    from dotenv import load_dotenv
    from elevenlabs.client import ElevenLabs

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY が .env に設定されていません")
    return ElevenLabs(api_key=api_key)


def read_csv_rows(filepath: str) -> list[dict]:
    """CSVを読んで [{serial, character, text}, ...] を返す。"""
    rows = []
    with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)  # ヘッダースキップ
        for row in reader:
            if len(row) < 3:
                continue
            try:
                serial = int(row[0])
            except ValueError:
                continue
            rows.append({
                "serial": serial,
                "character": row[1].strip(),
                "text": row[2].strip(),
            })
    return rows


def check_csv_alignment(split_path: str, elevenlabs_path: str) -> tuple[bool, list[str]]:
    """_split.csv と _elevenlabs.csv の整合性チェック。

    Returns:
        (ok, messages): ok=True なら続行可能
    """
    split_rows = read_csv_rows(split_path)
    el_rows = read_csv_rows(elevenlabs_path)

    messages = []
    messages.append(f"台本CSV（split）: {len(split_rows)}行")
    messages.append(f"ボイスCSV（elevenlabs）: {len(el_rows)}行")

    if len(split_rows) != len(el_rows):
        messages.append(f"⚠ 行数不一致！ (差: {abs(len(split_rows) - len(el_rows))}行)")

    mismatches = []
    max_rows = min(len(split_rows), len(el_rows))
    for i in range(max_rows):
        s = split_rows[i]
        e = el_rows[i]
        problems = []
        if s["serial"] != e["serial"]:
            problems.append(f"連番: {s['serial']}→{e['serial']}")
        if s["character"] != e["character"]:
            problems.append(f"キャラ: {s['character']}→{e['character']}")
        if problems:
            mismatches.append(f"  行{i+1}: {', '.join(problems)}")

    if mismatches:
        messages.append(f"⚠ {len(mismatches)}件の不一致:")
        messages.extend(mismatches[:20])
        if len(mismatches) > 20:
            messages.append(f"  ...他 {len(mismatches) - 20}件")
        ok = False
    else:
        if len(split_rows) == len(el_rows):
            messages.append("✓ 整合性OK: 連番・キャラ名すべて一致")
        else:
            messages.append("✓ 共通範囲の連番・キャラ名は一致（行数差あり）")
        ok = True

    return ok, messages
