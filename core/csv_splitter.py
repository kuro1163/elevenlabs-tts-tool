"""CSV複数キャラ行分割ロジック（GUI非依存）"""
import csv

from core.char_normalize import EXCLUDE_NAMES, normalize_char_name


def split_multi_character_rows(input_path: str, apply_normalization: bool = True):
    """CSVを読み込み、A列に複数キャラがある行を分割し、除外対象を削除する

    Returns: (rows, split_count, exclude_count, normalize_count)
    """
    rows = []
    split_count = 0
    exclude_count = 0
    normalize_count = 0
    serial_number = 1

    with open(input_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows.append(['連番'] + header)

        for row_num, row in enumerate(reader, start=2):
            if not row or not row[0].strip():
                continue

            char_name = row[0].strip()

            if '\n' in char_name or '・' in char_name:
                if '\n' in char_name:
                    characters = [c.strip() for c in char_name.split('\n') if c.strip()]
                else:
                    characters = [c.strip() for c in char_name.split('・') if c.strip()]

                if len(characters) > 1:
                    serif = row[1] if len(row) > 1 else ''
                    rest = row[2:] if len(row) > 2 else []

                    for char in characters:
                        if char in EXCLUDE_NAMES:
                            exclude_count += 1
                            print(f'  行{row_num}: 除外 ({char})')
                            continue
                        if apply_normalization:
                            normalized = normalize_char_name(char)
                            if normalized != char:
                                normalize_count += 1
                                char = normalized
                        new_row = [str(serial_number), char, serif] + rest
                        rows.append(new_row)
                        serial_number += 1

                    split_count += 1
                    print(f'  行{row_num}: {len(characters)}キャラに分割 ({", ".join(characters)})')
                    continue

            if char_name in EXCLUDE_NAMES:
                exclude_count += 1
                print(f'  行{row_num}: 除外 ({char_name})')
                continue

            if apply_normalization:
                normalized = normalize_char_name(char_name)
                if normalized != char_name:
                    normalize_count += 1
                    row = list(row)
                    row[0] = normalized

            rows.append([str(serial_number)] + row)
            serial_number += 1

    return rows, split_count, exclude_count, normalize_count
