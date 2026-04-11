"""キャラ名の正規化（表記ゆれ・括弧除去・除外判定）"""
import csv
import re

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
    '風紀委員会モブ': '風紀委員モブ',
    'ロボモブ': 'ロボ',
    'モブロボット': 'ロボ',
    'アリモブ': 'アリウスモブ',
    'アリウスモ': 'アリウスモブ',
    # シロコテラー表記ゆれ
    'シロコ・テラー': 'シロコテラー',
    'シロコテラ': 'シロコテラー',
    'テラーシロコ': 'シロコテラー',
    'テラシロコ': 'シロコテラー',
    'シロコ（テラー）': 'シロコテラー',
    'シロコ(テラー)': 'シロコテラー',
    # ヒナ派生
    'ヒナの黒い影': 'ヒナ',
    # その他よくある表記ゆれ
    'ナレーター': 'ナレーション',
    'パンちゃん': 'パンちゃん',
}


def normalize_char_name(name: str) -> str:
    """キャラ名を正規化する。マッピング → 括弧除去の順で変換"""
    if name in CHAR_NAME_ALIASES:
        return CHAR_NAME_ALIASES[name]
    stripped = re.sub(r'[（(][^）)]*[）)]', '', name).strip()
    if stripped and stripped != name:
        if stripped in CHAR_NAME_ALIASES:
            return CHAR_NAME_ALIASES[stripped]
        return stripped
    return name


def detect_name_normalizations(input_path: str) -> dict:
    """CSVを読み込み、正規化が必要なキャラ名を検出して一覧を返す

    Returns: dict of {元の名前: (正規化後の名前, 出現回数)}
    """
    normalizations = {}

    with open(input_path, 'r', encoding='utf-8-sig') as f:
        reader = csv.reader(f)
        next(reader)

        for row in reader:
            if not row or not row[0].strip():
                continue
            char_name = row[0].strip()

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
