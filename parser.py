"""
テキストパーサー: 台本形式のテキストからキャラ名とセリフを抽出
"""
import re
from dataclasses import dataclass


@dataclass
class DialogueLine:
    """1つのセリフを表すデータクラス"""
    index: int
    character: str
    text: str
    char_count: int


def clean_character_name(name: str) -> str:
    """キャラ名から（回想）などの注釈を除去"""
    cleaned = re.sub(r'[（(][^）)]*[）)]', '', name)
    return cleaned.strip()


def parse_dialogue(text: str) -> list[DialogueLine]:
    """
    台本形式のテキストをパースしてDialogueLineのリストを返す
    
    対応フォーマット:
    1. **①キャラ名**（XX字）+ コードブロック内のセリフ
    2. キャラ名\tセリフ\t文字数（タブ区切り）
    """
    lines = []
    
    # パターン1: **①キャラ名**（XX字）形式 + コードブロック
    pattern1 = r'\*\*[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚]?(\d*)([^\*]+)\*\*[（(](\d+)字[）)]'
    
    # コードブロックを含む全体のパターン
    block_pattern = r'\*\*([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚]?\d*)([^\*]+)\*\*[（(](\d+)字[）)]\s*```([^`]*)```'
    
    matches = re.findall(block_pattern, text, re.DOTALL)
    
    if matches:
        for i, match in enumerate(matches):
            index_str, character, char_count, dialogue = match
            character = character.strip()
            dialogue = dialogue.strip()
            
            lines.append(DialogueLine(
                index=i + 1,
                character=character,
                text=dialogue,
                char_count=int(char_count)
            ))
        return lines
    
    # パターン2: タブ区切り形式
    # 2a: キャラ名\tセリフ\t文字数（3カラム）
    # 2b: キャラ名\tセリフ（2カラム）
    # キャラ名が "〜\n〜" のようにダブルクォートで囲まれている場合にも対応
    
    # ダブルクォート内の改行を含むキャラ名に対応（3カラム）
    quoted_pattern_3col = r'"([^"]+)"\t([^\t]+)\t(\d+)'
    for match in re.finditer(quoted_pattern_3col, text):
        character, dialogue, char_count = match.groups()
        character = clean_character_name(character.replace('\n', ''))
        lines.append(DialogueLine(
            index=len(lines) + 1,
            character=character,
            text=dialogue.strip(),
            char_count=int(char_count)
        ))
    
    if lines:
        return lines
    
    # ダブルクォート内の改行を含むキャラ名に対応（2カラム）
    quoted_pattern_2col = r'"([^"]+)"\t([^\t\n]+)'
    for match in re.finditer(quoted_pattern_2col, text):
        character, dialogue = match.groups()
        character = clean_character_name(character.replace('\n', ''))
        lines.append(DialogueLine(
            index=len(lines) + 1,
            character=character,
            text=dialogue.strip(),
            char_count=len(dialogue.strip())
        ))
    
    if lines:
        return lines
    
    # 通常のタブ区切り（改行なしキャラ名）
    tab_pattern_3col = r'^([^\t\n]+)\t([^\t\n]+)\t(\d+)$'
    tab_pattern_2col = r'^([^\t\n]+)\t([^\t\n]+)$'
    
    for line in text.strip().split('\n'):
        match = re.match(tab_pattern_3col, line)
        if match:
            character, dialogue, char_count = match.groups()
            lines.append(DialogueLine(
                index=len(lines) + 1,
                character=clean_character_name(character),
                text=dialogue.strip(),
                char_count=int(char_count)
            ))
            continue
        
        match = re.match(tab_pattern_2col, line)
        if match:
            character, dialogue = match.groups()
            lines.append(DialogueLine(
                index=len(lines) + 1,
                character=clean_character_name(character),
                text=dialogue.strip(),
                char_count=len(dialogue.strip())
            ))
    
    if lines:
        return lines
    
    # パターン3: シンプルな **キャラ名** + 次行のセリフ
    simple_pattern = r'\*\*([①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮⑯⑰⑱⑲⑳㉑㉒㉓㉔㉕㉖㉗㉘㉙㉚]?)([^\*]+)\*\*[（(](\d+)字[）)]'
    
    parts = re.split(simple_pattern, text)
    
    if len(parts) > 1:
        idx = 1
        line_num = 0
        while idx < len(parts):
            if idx + 3 <= len(parts):
                line_num += 1
                character = parts[idx + 1].strip()
                char_count = int(parts[idx + 2])
                
                # 次のマッチまでのテキストをセリフとして取得
                dialogue_text = parts[idx + 3] if idx + 3 < len(parts) else ""
                
                # コードブロックがあれば抽出
                code_match = re.search(r'```([^`]*)```', dialogue_text)
                if code_match:
                    dialogue = code_match.group(1).strip()
                else:
                    # コードブロックがなければ次のパターンまでのテキスト
                    dialogue = dialogue_text.strip().split('\n')[0] if dialogue_text.strip() else ""
                
                if character and dialogue:
                    lines.append(DialogueLine(
                        index=line_num,
                        character=character,
                        text=dialogue,
                        char_count=char_count
                    ))
            idx += 4
    
    return lines


def parse_from_file(filepath: str) -> list[DialogueLine]:
    """ファイルから読み込んでパース"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return parse_dialogue(f.read())


if __name__ == "__main__":
    # テスト用サンプル
    sample_text = '''**①ヒナ**（90字）
```
私は、今日という日を生涯忘れることはないだろう(間)今日、2月14日の...
```

**②ホシノ**（51字）
```
え～、ではでは、指名されちゃったので...
```

**③ナレーション**（30字）
```
そして、物語は続いていく...
```
'''
    
    results = parse_dialogue(sample_text)
    for line in results:
        print(f"{line.index:03d}. [{line.character}] ({line.char_count}字)")
        print(f"    {line.text[:50]}..." if len(line.text) > 50 else f"    {line.text}")
        print()
