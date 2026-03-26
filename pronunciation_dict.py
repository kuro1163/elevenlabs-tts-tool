#!/usr/bin/env python3
"""
ElevenLabs 発音辞書管理ツール

辞書の作成・ルール追加・削除・一覧表示を行う。
config.json に辞書ID/version_IDを自動保存する。

使い方:
  python pronunciation_dict.py create              # 辞書を新規作成（初期ルール込み）
  python pronunciation_dict.py list                # 登録ルール一覧
  python pronunciation_dict.py add "流石" "さすが"  # ルール追加
  python pronunciation_dict.py remove "流石"        # ルール削除
  python pronunciation_dict.py sync                # config.jsonのversion_idを最新に更新
"""
import argparse
import json
import os
import sys

from dotenv import load_dotenv
from elevenlabs.client import ElevenLabs

from utils import load_config, save_config, get_client

BASE_DIR = os.path.dirname(__file__)

# 一律置換で安全な初期ルール（文脈依存しないもの）
INITIAL_RULES = [
    # 難読漢字 → ひらがな
    ("構って", "かまって"),
    ("貴方", "あなた"),
    ("穿いて", "はいて"),
    ("窃盗", "せっとう"),
    ("流石", "さすが"),
    ("済ませ", "すませ"),
    ("左手", "ひだりて"),
    ("間一髪", "かんいっぱつ"),
    ("微かに", "かすかに"),
    ("万事解決", "ばんじかいけつ"),
]

DICT_NAME = "blueaka-pronunciation-fixes"
DICT_DESCRIPTION = "ブルアカ動画用の読み間違い修正辞書（Alias: 漢字→ひらがな）"



def make_alias_rule(original: str, replacement: str, word_boundaries: bool = True) -> dict:
    rule = {
        "type": "alias",
        "string_to_replace": original,
        "alias": replacement,
    }
    if not word_boundaries:
        rule["word_boundaries"] = False
    return rule


def save_dict_to_config(config: dict, dict_id: str, version_id: str):
    """config.json に辞書情報を保存"""
    config["pronunciation_dictionary"] = {
        "id": dict_id,
        "version_id": version_id,
    }
    save_config(config)


# ══════════════════════════════════════════════════════════════════
# コマンド
# ══════════════════════════════════════════════════════════════════

def cmd_create(args):
    """辞書を新規作成（初期ルール込み）"""
    client = get_client()
    config = load_config()

    # 既存辞書があるか確認
    existing = config.get("pronunciation_dictionary", {})
    if existing.get("id"):
        print(f"既存の辞書があります: {existing['id']}")
        print("上書きしますか？ [y/N]: ", end="")
        if input().strip().lower() != "y":
            print("キャンセル")
            return

    rules = [make_alias_rule(orig, repl) for orig, repl in INITIAL_RULES]

    print(f"辞書を作成中... ({len(rules)}件のルール)")
    result = client.pronunciation_dictionaries.create_from_rules(
        rules=rules,
        name=DICT_NAME,
        description=DICT_DESCRIPTION,
    )

    save_dict_to_config(config, result.id, result.version_id)

    print(f"\n辞書作成完了:")
    print(f"  ID:         {result.id}")
    print(f"  version_id: {result.version_id}")
    print(f"  ルール数:   {result.version_rules_num}")
    print(f"\nconfig.json に保存しました")

    # ルール一覧表示
    print(f"\n登録ルール:")
    for orig, repl in INITIAL_RULES:
        print(f"  {orig} → {repl}")


def cmd_list(args):
    """登録ルール一覧を表示"""
    client = get_client()
    config = load_config()

    dict_config = config.get("pronunciation_dictionary", {})
    dict_id = dict_config.get("id")
    if not dict_id:
        print("辞書が未作成です。`python pronunciation_dict.py create` で作成してください。")
        return

    detail = client.pronunciation_dictionaries.get(
        pronunciation_dictionary_id=dict_id
    )

    print(f"辞書: {detail.name}")
    print(f"  ID:         {detail.id}")
    print(f"  version_id: {detail.latest_version_id}")
    print(f"  ルール数:   {detail.latest_version_rules_num}")
    print()

    if hasattr(detail, "rules") and detail.rules:
        print("ルール一覧:")
        for rule in detail.rules:
            rule_type = rule.type if hasattr(rule, "type") else "?"
            original = rule.string_to_replace if hasattr(rule, "string_to_replace") else "?"
            if rule_type == "alias":
                replacement = rule.alias if hasattr(rule, "alias") else "?"
                print(f"  {original} → {replacement}")
            else:
                print(f"  {original} (phoneme: {rule.phoneme if hasattr(rule, 'phoneme') else '?'})")
    else:
        print("(ルール詳細を取得できませんでした)")

    # config.json の version_id が古い場合は更新
    if dict_config.get("version_id") != detail.latest_version_id:
        config["pronunciation_dictionary"]["version_id"] = detail.latest_version_id
        save_config(config)
        print(f"\nconfig.json の version_id を更新しました → {detail.latest_version_id}")


def cmd_add(args):
    """ルールを追加"""
    client = get_client()
    config = load_config()

    dict_config = config.get("pronunciation_dictionary", {})
    dict_id = dict_config.get("id")
    if not dict_id:
        print("辞書が未作成です。`python pronunciation_dict.py create` で作成してください。")
        return

    rule = make_alias_rule(args.original, args.replacement)
    print(f"ルール追加: {args.original} → {args.replacement}")

    result = client.pronunciation_dictionaries.rules.add(
        pronunciation_dictionary_id=dict_id,
        rules=[rule],
    )

    # version_id を更新
    config["pronunciation_dictionary"]["version_id"] = result.version_id
    save_config(config)

    print(f"  version_id: {result.version_id}")
    print(f"  ルール数:   {result.version_rules_num}")


def cmd_remove(args):
    """ルールを削除"""
    client = get_client()
    config = load_config()

    dict_config = config.get("pronunciation_dictionary", {})
    dict_id = dict_config.get("id")
    if not dict_id:
        print("辞書が未作成です。")
        return

    print(f"ルール削除: {args.original}")

    result = client.pronunciation_dictionaries.rules.remove(
        pronunciation_dictionary_id=dict_id,
        rule_strings=[args.original],
    )

    config["pronunciation_dictionary"]["version_id"] = result.version_id
    save_config(config)

    print(f"  version_id: {result.version_id}")
    print(f"  ルール数:   {result.version_rules_num}")


def cmd_sync(args):
    """config.json の version_id を最新に更新"""
    client = get_client()
    config = load_config()

    dict_config = config.get("pronunciation_dictionary", {})
    dict_id = dict_config.get("id")
    if not dict_id:
        print("辞書が未作成です。")
        return

    detail = client.pronunciation_dictionaries.get(
        pronunciation_dictionary_id=dict_id
    )

    old_version = dict_config.get("version_id", "(なし)")
    new_version = detail.latest_version_id

    if old_version == new_version:
        print(f"version_id は最新です: {new_version}")
    else:
        config["pronunciation_dictionary"]["version_id"] = new_version
        save_config(config)
        print(f"version_id を更新: {old_version} → {new_version}")


def cmd_bulk_add(args):
    """TSVファイルから一括追加（形式: 原文<TAB>読み）"""
    client = get_client()
    config = load_config()

    dict_config = config.get("pronunciation_dictionary", {})
    dict_id = dict_config.get("id")
    if not dict_id:
        print("辞書が未作成です。")
        return

    rules = []
    with open(args.file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                rules.append(make_alias_rule(parts[0], parts[1], word_boundaries=not args.no_word_boundaries))

    if not rules:
        print("追加するルールがありません")
        return

    print(f"{len(rules)}件のルールを追加します:")
    for r in rules:
        print(f"  {r['string_to_replace']} → {r['alias']}")

    # APIは1リクエスト100件まで → バッチ分割
    BATCH_SIZE = 100
    result = None
    for i in range(0, len(rules), BATCH_SIZE):
        batch = rules[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(rules) + BATCH_SIZE - 1) // BATCH_SIZE
        if total_batches > 1:
            print(f"\nバッチ {batch_num}/{total_batches} ({len(batch)}件)...")
        result = client.pronunciation_dictionaries.rules.add(
            pronunciation_dictionary_id=dict_id,
            rules=batch,
        )

    config["pronunciation_dictionary"]["version_id"] = result.version_id
    save_config(config)

    print(f"\n追加完了: ルール数 {result.version_rules_num}")


def main():
    parser = argparse.ArgumentParser(
        description="ElevenLabs 発音辞書管理ツール",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("create", help="辞書を新規作成（初期ルール込み）")
    sub.add_parser("list", help="登録ルール一覧")
    sub.add_parser("sync", help="config.jsonのversion_idを最新に更新")

    p_add = sub.add_parser("add", help="ルール追加")
    p_add.add_argument("original", help="置換対象の文字列")
    p_add.add_argument("replacement", help="置換後の文字列")

    p_remove = sub.add_parser("remove", help="ルール削除")
    p_remove.add_argument("original", help="削除するルールの置換対象文字列")

    p_bulk = sub.add_parser("bulk-add", help="TSVファイルから一括追加")
    p_bulk.add_argument("file", help="TSVファイルパス（原文<TAB>読み）")
    p_bulk.add_argument("--no-word-boundaries", action="store_true", help="単語境界なしで登録（日本語苗字向け）")

    args = parser.parse_args()

    commands = {
        "create": cmd_create,
        "list": cmd_list,
        "add": cmd_add,
        "remove": cmd_remove,
        "sync": cmd_sync,
        "bulk-add": cmd_bulk_add,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
