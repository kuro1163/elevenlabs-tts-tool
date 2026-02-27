#!/usr/bin/env python3
"""
YMM4 自動配置ツール
ElevenLabsで生成した音声ファイル群を読み込み、YMM4のタイムラインに自動配置した.ymmpファイルを出力する
"""

import json
import os
import glob
import argparse

try:
    from mutagen.mp3 import MP3
except ImportError:
    print("mutagenがインストールされていません。以下のコマンドでインストールしてください:")
    print("  pip install mutagen")
    exit(1)


def parse_filename(filename: str) -> dict:
    """ファイル名から連番・キャラ名・セリフを抽出
    
    形式: {連番}_{キャラ名}_{セリフ}.mp3
    例: 1_キリノ_ありがとうございます.mp3
    """
    name = filename.rsplit('.', 1)[0]
    parts = name.split('_', 2)
    return {
        'index': int(parts[0]),
        'character': parts[1],
        'serif': parts[2] if len(parts) > 2 else ''
    }


def get_audio_duration(filepath: str) -> float:
    """mp3の長さを秒で返す"""
    return MP3(filepath).info.length


def seconds_to_ymm4_time(seconds: float) -> str:
    """秒をYMM4のTimeSpan形式に変換（HH:MM:SS.fffffff）"""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:010.7f}"


def make_anim_param(value: float) -> dict:
    """YMM4のアニメーションパラメータを生成"""
    return {
        "Values": [{"Value": value}],
        "Span": 0.0,
        "AnimationType": "なし",
        "Bezier": {
            "Points": [
                {
                    "Point": {"X": 0.0, "Y": 0.0},
                    "ControlPoint1": {"X": -0.3, "Y": -0.3},
                    "ControlPoint2": {"X": 0.3, "Y": 0.3}
                },
                {
                    "Point": {"X": 1.0, "Y": 1.0},
                    "ControlPoint1": {"X": -0.3, "Y": -0.3},
                    "ControlPoint2": {"X": 0.3, "Y": 0.3}
                }
            ],
            "IsQuadratic": False
        }
    }


def create_voice_item(char_name: str, serif: str, audio_path_win: str, 
                      voice_length_str: str, frame: int, layer: int, 
                      length_frames: int, volume: float = 50.0, 
                      x: float = 0.0, y: float = 530.0,
                      font_size: float = 45.0,
                      font_color: str = "#FFFFFFFF", 
                      style_color: str = "#FF8B0000") -> dict:
    """ElevenLabsカスタム音声用VoiceItemを生成"""
    return {
        "$type": "YukkuriMovieMaker.Project.Items.VoiceItem, YukkuriMovieMaker",
        "IsWaveformEnabled": False,
        "CharacterName": char_name,
        "Serif": serif,
        "Decorations": [],
        "Hatsuon": audio_path_win,
        "Pronounce": None,
        "LipSyncFrames": [],
        "VoiceCache": None,
        "VoiceLength": voice_length_str,
        "Volume": make_anim_param(volume),
        "Pan": make_anim_param(0.0),
        "PlaybackRate": 100.0,
        "VoiceParameter": {
            "$type": "YukkuriMovieMaker.Voice.AquesTalk1VoiceParameter, YukkuriMovieMaker",
            "Speed": 100,
            "EngineVersion": "V1_7"
        },
        "ContentOffset": "00:00:00",
        "VoiceFadeIn": 0.0,
        "VoiceFadeOut": 0.0,
        "EchoIsEnabled": False,
        "EchoInterval": 0.1,
        "EchoAttenuation": 40.0,
        "AudioEffects": [],
        "JimakuVisibility": "UseCharacterSetting",
        "X": make_anim_param(x),
        "Y": make_anim_param(y),
        "Z": make_anim_param(0.0),
        "Opacity": make_anim_param(100.0),
        "Zoom": make_anim_param(100.0),
        "Rotation": make_anim_param(0.0),
        "JimakuFadeIn": 0.0,
        "JimakuFadeOut": 0.0,
        "Blend": "Normal",
        "IsInverted": False,
        "IsClippingWithObjectAbove": False,
        "IsAlwaysOnTop": False,
        "IsZOrderEnabled": False,
        "Font": "メイリオ",
        "FontSize": make_anim_param(font_size),
        "LineHeight2": make_anim_param(100.0),
        "LetterSpacing2": make_anim_param(0.0),
        "WordWrap": "NoWrap",
        "MaxWidth": make_anim_param(1920.0),
        "BasePoint": "CenterBottom",
        "FontColor": font_color,
        "Style": "Border",
        "StyleColor": style_color,
        "Bold": False,
        "Italic": False,
        "IsTrimEndSpace": False,
        "IsDevidedPerCharacter": False,
        "DisplayInterval": 0.0,
        "DisplayDirection": "FromFirst",
        "HideInterval": 0.0,
        "HideDirection": "FromFirst",
        "JimakuVideoEffects": [],
        "TachieFaceParameter": None,
        "TachieFaceEffects": [],
        "Group": 0,
        "Frame": frame,
        "Layer": layer,
        "KeyFrames": {"Frames": [], "Count": 0},
        "Length": length_frames,
        "PlaybackRate": 100.0,
        "ContentOffset": "00:00:00",
        "Remark": "",
        "IsLocked": False,
        "IsHidden": False
    }


def assign_layers(voice_entries: list) -> dict:
    """キャラの登場順にレイヤー番号を割り当て"""
    char_layers = {}
    next_layer = 0
    for entry in voice_entries:
        char = entry['character']
        if char not in char_layers:
            char_layers[char] = next_layer
            next_layer += 1
    return char_layers


def calculate_frames(voice_entries: list, audio_dir: str, gap_frames: int = 18) -> list:
    """各セリフのFrame位置とLengthを計算"""
    current_frame = 0
    for entry in voice_entries:
        filepath = os.path.join(audio_dir, entry['filename'])
        duration = get_audio_duration(filepath)
        length_frames = int(duration * 60)
        
        entry['frame'] = current_frame
        entry['length'] = length_frames
        entry['duration'] = duration
        entry['voice_length'] = seconds_to_ymm4_time(duration)
        
        current_frame += length_frames + gap_frames
    return voice_entries


def get_char_settings(template_data: dict) -> dict:
    """テンプレートからキャラ設定をdict化"""
    settings = {}
    for c in template_data.get('Characters', []):
        settings[c['Name']] = {
            'font_color': c.get('FontColor', '#FFFFFFFF'),
            'style_color': c.get('StyleColor', '#FF8B0000'),
            'font': c.get('Font', 'メイリオ'),
            'color': c.get('Color', '#FFFFFFFF'),
            'y': c.get('Y', {}).get('Values', [{}])[0].get('Value', 530.0),
        }
    return settings


def save_ymmp(data: dict, output_path: str):
    """BOM付きUTF-8で保存"""
    with open(output_path, 'w', encoding='utf-8-sig') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def generate_ymmp(template_path: str, audio_dir: str, output_path: str, 
                  voice_base_dir_win: str, gap_seconds: float = 0.3,
                  default_volume: float = 50.0):
    """
    YMM4用.ymmpファイルを生成
    
    Args:
        template_path: テンプレート.ymmpのパス
        audio_dir: 音声フォルダのローカルパス
        output_path: 出力.ymmpのパス
        voice_base_dir_win: Windowsでの音声フォルダパス
            例: "D:\\YMM4編集\\ブルアカ教室\\ボイス\\台本名"
        gap_seconds: セリフ間の間隔（秒）
        default_volume: デフォルト音量
    """
    # 1. テンプレート読み込み
    print(f"テンプレート読み込み: {template_path}")
    with open(template_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)
    
    # 2. 音声ファイル一覧（連番順ソート）
    mp3_pattern = os.path.join(audio_dir, '*.mp3')
    mp3_files = sorted(
        glob.glob(mp3_pattern),
        key=lambda x: int(os.path.basename(x).split('_')[0])
    )
    
    if not mp3_files:
        print(f"エラー: 音声ファイルが見つかりません: {mp3_pattern}")
        return
    
    print(f"音声ファイル数: {len(mp3_files)}")
    
    # 3. パース
    entries = []
    for fp in mp3_files:
        fn = os.path.basename(fp)
        try:
            parsed = parse_filename(fn)
            parsed['filename'] = fn
            parsed['filepath'] = fp
            entries.append(parsed)
        except (ValueError, IndexError) as e:
            print(f"警告: ファイル名のパースに失敗: {fn} - {e}")
            continue
    
    if not entries:
        print("エラー: 有効な音声ファイルがありません")
        return
    
    # 4. レイヤー割り当て
    char_layers = assign_layers(entries)
    
    # 5. Frame計算
    gap_frames = int(gap_seconds * 60)
    calculate_frames(entries, audio_dir, gap_frames)
    
    # 6. キャラ設定取得
    char_settings = get_char_settings(data)
    
    # テンプレートに登録されているキャラ名一覧
    registered_chars = set(char_settings.keys())
    
    # 7. VoiceItem生成
    voice_items = []
    missing_chars = set()
    
    for entry in entries:
        char = entry['character']
        
        # キャラがテンプレートに登録されているかチェック
        if char not in registered_chars:
            missing_chars.add(char)
        
        settings = char_settings.get(char, {})
        
        # Windowsパス生成
        audio_path_win = voice_base_dir_win + '\\' + entry['filename']
        
        item = create_voice_item(
            char_name=char,
            serif=entry['serif'],
            audio_path_win=audio_path_win,
            voice_length_str=entry['voice_length'],
            frame=entry['frame'],
            layer=char_layers[char],
            length_frames=entry['length'],
            volume=default_volume,
            y=settings.get('y', 530.0),
            font_color=settings.get('font_color', '#FFFFFFFF'),
            style_color=settings.get('style_color', '#FF8B0000'),
        )
        voice_items.append(item)
    
    # 未登録キャラの警告
    if missing_chars:
        print(f"\n警告: 以下のキャラクターがテンプレートに登録されていません:")
        for char in sorted(missing_chars):
            print(f"  - {char}")
        print("YMM4で開いた際にデフォルト設定が適用されます。\n")
    
    # 8. タイムラインに配置（既存Itemsをクリアして新規追加）
    data['Timelines'][0]['Items'] = voice_items
    
    # タイムラインの長さを更新
    if entries:
        last = entries[-1]
        data['Timelines'][0]['Length'] = last['frame'] + last['length'] + 60
    
    # 9. 出力
    save_ymmp(data, output_path)
    
    # 結果表示
    print(f"\n生成完了: {output_path}")
    print(f"  セリフ数: {len(voice_items)}")
    print(f"  キャラ数: {len(char_layers)}")
    print(f"  レイヤー割り当て:")
    for char, layer in char_layers.items():
        print(f"    Layer {layer}: {char}")
    
    # 総時間を計算
    if entries:
        total_seconds = (last['frame'] + last['length']) / 60
        minutes = int(total_seconds // 60)
        seconds = total_seconds % 60
        print(f"  総時間: {minutes}分{seconds:.1f}秒")


def load_config(config_path: str = None) -> dict:
    """設定ファイルを読み込む"""
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    
    if os.path.exists(config_path):
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def main():
    parser = argparse.ArgumentParser(
        description='YMM4 自動配置ツール - ElevenLabs音声をYMM4タイムラインに配置',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用例:
  python ymm4_generate.py --audio-dir ./output --script-name "バレンタイン台本"
  python ymm4_generate.py --audio-dir D:\\voices --template D:\\template.ymmp --output D:\\result.ymmp
        """
    )
    
    parser.add_argument(
        '--audio-dir', '-a',
        help='音声フォルダのパス（省略時はconfig.jsonのoutput_directoryを使用）'
    )
    
    parser.add_argument(
        '--script-name', '-s',
        help='台本名（出力ファイル名とWindowsパスに使用）'
    )
    
    parser.add_argument(
        '--template', '-t',
        help='テンプレート.ymmpのパス（省略時はconfig.jsonから読み込み）'
    )
    
    parser.add_argument(
        '--output', '-o',
        help='出力.ymmpのパス（省略時は台本名.ymmp）'
    )
    
    parser.add_argument(
        '--voice-base-dir', '-v',
        help='Windowsでの音声フォルダの基底パス（省略時はconfig.jsonから読み込み）'
    )
    
    parser.add_argument(
        '--gap', '-g',
        type=float,
        default=None,
        help='セリフ間の間隔（秒）。デフォルト: 0.3'
    )
    
    parser.add_argument(
        '--volume',
        type=float,
        default=None,
        help='音量。デフォルト: 50.0'
    )
    
    parser.add_argument(
        '--config', '-c',
        help='設定ファイルのパス'
    )
    
    args = parser.parse_args()
    
    # 設定ファイル読み込み
    config = load_config(args.config)
    ymm4_config = config.get('ymm4', {})
    
    # テンプレートパス
    template_path = args.template or ymm4_config.get('template_path')
    if not template_path:
        print("エラー: テンプレートパスを指定してください（--template または config.json の ymm4.template_path）")
        return
    
    # 音声フォルダのWindowsパス
    voice_base_dir_win = args.voice_base_dir or ymm4_config.get('voice_base_dir_win')
    if not voice_base_dir_win:
        print("エラー: Windowsでの音声フォルダパスを指定してください（--voice-base-dir または config.json の ymm4.voice_base_dir_win）")
        return
    
    # 台本名がある場合はパスに追加
    if args.script_name:
        voice_base_dir_win = voice_base_dir_win.rstrip('\\') + '\\' + args.script_name
    
    # 音声フォルダ（ローカル）
    audio_dir = args.audio_dir or config.get('output_directory', './output/')
    
    # 出力パス
    output_path = args.output
    if not output_path:
        if args.script_name:
            output_path = f"{args.script_name}.ymmp"
        else:
            output_path = "output.ymmp"
    
    # 間隔
    gap_seconds = args.gap if args.gap is not None else ymm4_config.get('gap_seconds', 0.3)
    
    # 音量
    volume = args.volume if args.volume is not None else ymm4_config.get('default_volume', 50.0)
    
    # 生成実行
    generate_ymmp(
        template_path=template_path,
        audio_dir=audio_dir,
        output_path=output_path,
        voice_base_dir_win=voice_base_dir_win,
        gap_seconds=gap_seconds,
        default_volume=volume
    )


if __name__ == '__main__':
    main()
