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

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# core パッケージから re-export（互換性維持）
from core.char_normalize import (
    EXCLUDE_NAMES, CHAR_NAME_ALIASES,
    normalize_char_name, detect_name_normalizations,
)
from core.csv_splitter import split_multi_character_rows


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
