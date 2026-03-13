import sys, os, csv
sys.path.insert(0, 'D:/cursor/elevenlabs-tts-tool')
from elevenlabs_gui import split_csv

src = 'D:/User/Downloads/【ブルアカ】ペア組んでねへのコメント(その1).csv'
voice_base_dir = 'D:/YMM4編集/ブルアカ教室/ボイス'

stem = os.path.splitext(os.path.basename(src))[0]
project_dir = os.path.join(voice_base_dir, stem)
script_dir  = os.path.join(project_dir, '台本')
split_path  = os.path.join(script_dir, f'{stem}_split.csv')

os.makedirs(script_dir, exist_ok=True)

rows, split_count, exclude_count = split_csv(src)

with open(split_path, 'w', encoding='utf-8-sig', newline='') as f:
    writer = csv.writer(f)
    for row in rows:
        writer.writerow(row)

print(f'プロジェクトフォルダ: {project_dir}')
print(f'台本フォルダ:         {script_dir}')
print(f'分割CSV:              {split_path}')
print(f'存在確認: {os.path.exists(split_path)}')
print(f'データ行数: {len(rows)-1}  除外: {exclude_count}')
