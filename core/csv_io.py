"""CSV読み込み・整合性チェック"""
import csv


def read_csv_rows(filepath: str) -> list[dict]:
    """CSVを読んで [{serial, character, text}, ...] を返す。"""
    rows = []
    with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        next(reader, None)
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
    """_split.csv と _elevenlabs.csv の整合性チェック。"""
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
