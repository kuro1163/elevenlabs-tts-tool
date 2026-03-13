import sys
sys.path.insert(0, 'D:/cursor/elevenlabs-tts-tool')
from elevenlabs_gui import split_csv
from parser import parse_from_csv
import csv, tempfile, os

src = 'D:/User/Downloads/【ブルアカ】ペア組んでねへのコメント(その1).csv'

print('=== split_csv テスト ===')
rows, split_count, exclude_count = split_csv(src)
print(f'ヘッダー: {rows[0]}')
print(f'データ行数: {len(rows)-1}  分割: {split_count}  除外: {exclude_count}')
print()
print('先頭5行:')
for r in rows[1:6]:
    print(' ', r)

# 一時CSVに書いてparse_from_csvもテスト
print()
print('=== parse_from_csv テスト ===')
with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8-sig', suffix='.csv', delete=False, newline='') as f:
    writer = csv.writer(f)
    for r in rows:
        writer.writerow(r)
    tmp = f.name

dialogues = parse_from_csv(tmp)
print(f'セリフ件数: {len(dialogues)}')
print('先頭5件:')
for d in dialogues[:5]:
    print(f'  {d.index:03d}. [{d.character}] {d.text[:30]}')
os.unlink(tmp)
