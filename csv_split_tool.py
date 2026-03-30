"""
CSV複数キャラ行分割ツール v5
- A列に改行で複数キャラ名がある行を、同じセリフで複数行に展開する
- 霊夢・魔理沙・場面転換の行を除外する
- B列（セリフ）内の改行は保持する（YMM4テロップ表示用）
- 先頭に連番列を追加（ボイスファイルとの照合用）
"""

import csv
import tkinter as tk
from tkinter import filedialog, messagebox
import os
import sys

# 除外するキャラ名・行のリスト
EXCLUDE_NAMES = ['霊夢', '魔理沙', 'ブルアカ霊夢', 'ブルアカ魔理沙', '場面転換', 'アイキャッチ']

# キャラ名の正規化マッピング（略称/表記ゆれ → 登録名）
CHAR_NAME_ALIASES = {
    # モブ系
    'トリニティモブ': 'トリモブ',
    'トリモ': 'トリモブ',
    'ヴァルモブ': 'ヴァルキューレモブ',
    'ヴァルモ': 'ヴァルキューレモブ',
    '誠実モブ': '正実モブ',
    'まさみモブ': '正実モブ',
    'マサミモブ': '正実モブ',
    'ゲヘモブ': 'ゲヘナモブ',
    'アリモブ': 'アリウスモブ',
    'アリウスモ': 'アリウスモブ',
    # シロコテラー表記ゆれ
    'シロコ・テラー': 'シロコテラー',
    'シロコテラ': 'シロコテラー',
    'テラーシロコ': 'シロコテラー',
    'テラシロコ': 'シロコテラー',
    'シロコ（テラー）': 'シロコテラー',
    'シロコ(テラー)': 'シロコテラー',
    # その他よくある表記ゆれ
    'ナレーター': 'ナレーション',
    'パンちゃん': 'パンちゃん',
}


def normalize_char_name(name):
    """キャラ名を正規化する。マッピング → 括弧除去の順で変換"""
    # 1. 完全一致マッピング
    if name in CHAR_NAME_ALIASES:
        return CHAR_NAME_ALIASES[name]
    # 2. 括弧付きキャラ名の除去: 先生(裏垢)→先生, コタマ(DM)→コタマ
    import re
    stripped = re.sub(r'[（(][^）)]*[）)]', '', name).strip()
    if stripped and stripped != name:
        # 括弧除去後がマッピングにあればそちらを返す
        if stripped in CHAR_NAME_ALIASES:
            return CHAR_NAME_ALIASES[stripped]
        return stripped
    return name


def detect_name_normalizations(input_path):
    """CSVを読み込み、正規化が必要なキャラ名を検出して一覧を返す

    Returns: dict of {元の名前: (正規化後の名前, 出現回数)}
    """
    normalizations = {}

    with open(input_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader)  # ヘッダースキップ

        for row in reader:
            if not row or not row[0].strip():
                continue
            char_name = row[0].strip()

            # 改行または「・」で複数キャラの場合、それぞれチェック
            names = [char_name]
            if '\n' in char_name:
                names = [c.strip() for c in char_name.split('\n') if c.strip()]
            elif '・' in char_name:
                names = [c.strip() for c in char_name.split('・') if c.strip()]

            for name in names:
                if name in EXCLUDE_NAMES:
                    continue
                normalized = normalize_char_name(name)
                if normalized != name:
                    if name not in normalizations:
                        normalizations[name] = (normalized, 0)
                    normalizations[name] = (normalizations[name][0], normalizations[name][1] + 1)

    return normalizations


def split_multi_character_rows(input_path, apply_normalization=True):
    """CSVを読み込み、A列に複数キャラがある行を分割し、除外対象を削除する

    出力形式: 連番,キャラ名,セリフ,文字数,...
    連番はボイスファイル名の連番と一致させるため、1から順に振る
    apply_normalization: Trueの場合、キャラ名を正規化する
    """

    rows = []
    split_count = 0
    exclude_count = 0
    normalize_count = 0
    serial_number = 1  # 連番カウンター

    with open(input_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)
        # ヘッダーに連番列を追加
        rows.append(['連番'] + header)

        for row_num, row in enumerate(reader, start=2):
            if not row or not row[0].strip():
                continue  # 空行はスキップ

            char_name = row[0].strip()

            # A列に改行または「・」が含まれているか確認（複数キャラ分割）
            if '\n' in char_name or '・' in char_name:
                if '\n' in char_name:
                    characters = [c.strip() for c in char_name.split('\n') if c.strip()]
                else:
                    characters = [c.strip() for c in char_name.split('・') if c.strip()]

                if len(characters) > 1:
                    serif = row[1] if len(row) > 1 else ''
                    rest = row[2:] if len(row) > 2 else []

                    for char in characters:
                        # 除外対象チェック
                        if char in EXCLUDE_NAMES:
                            exclude_count += 1
                            print(f'  行{row_num}: 除外 ({char})')
                            continue
                        # キャラ名正規化
                        if apply_normalization:
                            normalized = normalize_char_name(char)
                            if normalized != char:
                                normalize_count += 1
                                char = normalized
                        # 連番を先頭に追加
                        new_row = [str(serial_number), char, serif] + rest
                        rows.append(new_row)
                        serial_number += 1

                    split_count += 1
                    print(f'  行{row_num}: {len(characters)}キャラに分割 ({", ".join(characters)})')
                    continue

            # 除外対象チェック（単一キャラ行）
            if char_name in EXCLUDE_NAMES:
                exclude_count += 1
                print(f'  行{row_num}: 除外 ({char_name})')
                continue

            # キャラ名正規化
            if apply_normalization:
                normalized = normalize_char_name(char_name)
                if normalized != char_name:
                    normalize_count += 1
                    row = list(row)
                    row[0] = normalized

            # 連番を先頭に追加
            rows.append([str(serial_number)] + row)
            serial_number += 1

    return rows, split_count, exclude_count, normalize_count


def main():
    root = tk.Tk()
    root.withdraw()
    
    # 入力ファイル選択
    input_path = filedialog.askopenfilename(
        title='分割するCSVを選択',
        filetypes=[('CSV files', '*.csv'), ('All files', '*.*')]
    )
    
    if not input_path:
        print('キャンセルされました')
        return
    
    print(f'入力: {input_path}')
    print(f'除外対象: {", ".join(EXCLUDE_NAMES)}')
    print()
    
    # 分割処理
    rows, split_count, exclude_count, normalize_count = split_multi_character_rows(input_path)

    # 出力ファイル名（元ファイル名_split.csv）
    base, ext = os.path.splitext(input_path)
    output_path = f'{base}_split{ext}'

    # 出力
    with open(output_path, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        for row in rows:
            writer.writerow(row)

    total_rows = len(rows) - 1  # ヘッダー除く
    msg = f'完了!\n\n分割した行: {split_count}行\n除外した行: {exclude_count}行\n名前正規化: {normalize_count}行\n出力行数: {total_rows}行\n出力先: {output_path}'
    print(f'\n{msg}')
    messagebox.showinfo('完了', msg)


if __name__ == '__main__':
    main()
