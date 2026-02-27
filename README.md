# ElevenLabs TTS Generator

キャラ名とセリフをコピペ → 自動でキャラごとのvoice_idに紐づけ → ElevenLabs APIで音声生成するツール

**YMM4自動配置機能付き**: 生成した音声をYMM4のタイムラインに自動配置できます

## セットアップ

### 1. 依存パッケージのインストール

```bash
cd elevenlabs-tts-tool
pip install -r requirements.txt
```

### 2. APIキーの設定

`.env.example` をコピーして `.env` を作成し、ElevenLabsのAPIキーを設定:

```bash
cp .env.example .env
```

```
ELEVENLABS_API_KEY=your_api_key_here
```

### 3. Voice IDの取得と設定

#### config.jsonを作成

```bash
cp config.example.json config.json
```

#### Voice ID一覧を取得

```bash
python generate.py --list-voices
```

#### config.jsonにマッピングを設定

`config.json` の `character_voices` にキャラ名とvoice_idの対応を設定:

```json
{
    "character_voices": {
        "キャラ名1": "your_voice_id_here",
        "キャラ名2": "your_voice_id_here",
        "ナレーション": "your_voice_id_here"
    }
}
```

## 使い方

### 基本的な使い方

```bash
python generate.py
```

実行後、台本テキストをコピペして入力（空行を2回入力で確定）

### 入力フォーマット

以下の形式に対応:

**形式1: マークダウン + コードブロック**
```
**①ヒナ**（90字）
```
私は、今日という日を生涯忘れることはないだろう
```

**②ホシノ**（51字）
```
え～、ではでは、指名されちゃったので...
```
```

**形式2: タブ区切り**
```
ヒナ	私は、今日という日を生涯忘れることはないだろう	45
ホシノ	え～、ではでは、指名されちゃったので...	23
```

### 確認なしで実行

```bash
python generate.py -y
```

### 出力

`output/` フォルダに連番ファイルとして保存:
- `1_ヒナ_セリフ内容.mp3`
- `2_ホシノ_セリフ内容.mp3`
- `3_ナレーション_セリフ内容.mp3`

## 設定オプション (config.json)

| キー | 説明 | デフォルト |
|------|------|-----------|
| `character_voices` | キャラ名→voice_idのマッピング | - |
| `default_model` | 使用するモデル | `eleven_v3` |
| `default_output_format` | 出力フォーマット | `mp3_44100_128` |
| `language_code` | 言語コード | `ja` |
| `output_directory` | 出力先ディレクトリ | `./output/` |

## 利用可能なモデル

| モデルID | 特徴 |
|----------|------|
| `eleven_v3` | 最新・最高品質・感情表現◎（推奨） |
| `eleven_multilingual_v2` | 安定・高品質 |
| `eleven_flash_v2_5` | 超低遅延75ms |
| `eleven_turbo_v2_5` | 低遅延バランス型 |

---

## YMM4 自動配置ツール

生成した音声ファイルをYMM4（ゆっくりMovieMaker4）のタイムラインに自動配置します。

### YMM4用の設定

`config.json` に以下を追加:

```json
{
    "ymm4": {
        "template_path": "D:\\YMM4編集\\テンプレート.ymmp",
        "voice_base_dir_win": "D:\\YMM4編集\\ボイス",
        "gap_seconds": 0.3,
        "default_volume": 50.0
    }
}
```

| キー | 説明 |
|------|------|
| `template_path` | キャラ登録済みのテンプレート.ymmpファイルのパス |
| `voice_base_dir_win` | YMM4から見た音声フォルダの基底パス |
| `gap_seconds` | セリフ間の間隔（秒） |
| `default_volume` | デフォルト音量 |

### 使い方

```bash
# 基本的な使い方（output/フォルダの音声を使用）
python ymm4_generate.py --script-name "台本名"

# 音声フォルダを指定
python ymm4_generate.py --audio-dir ./output --script-name "バレンタイン台本"

# すべてのオプションを指定
python ymm4_generate.py --audio-dir D:\voices --template D:\template.ymmp --output D:\result.ymmp
```

### オプション

| オプション | 説明 |
|-----------|------|
| `--audio-dir`, `-a` | 音声フォルダのパス（省略時: config.jsonのoutput_directory） |
| `--script-name`, `-s` | 台本名（出力ファイル名とWindowsパスに使用） |
| `--template`, `-t` | テンプレート.ymmpのパス |
| `--output`, `-o` | 出力.ymmpのパス |
| `--voice-base-dir`, `-v` | Windowsでの音声フォルダパス |
| `--gap`, `-g` | セリフ間の間隔（秒） |
| `--volume` | 音量 |

### 出力ファイル形式

`generate.py` の出力形式に対応:
```
1_キリノ_ありがとうございます.mp3
2_ヴァルキューレモブ_こちらこそよろしく.mp3
3_キリノ_それでは始めましょう.mp3
```

### 機能

- テンプレートからキャラクター設定（字幕色など）を自動継承
- キャラの登場順でレイヤーを自動割り当て
- 音声の長さを取得してFrame位置を自動計算
- セリフ間の間隔を設定可能
- テンプレートに未登録のキャラがある場合は警告表示

### ワークフロー

```bash
# 1. ElevenLabsで音声生成
python generate.py

# 2. YMM4用.ymmpを生成
python ymm4_generate.py --script-name "バレンタイン台本"

# 3. 生成された.ymmpをYMM4で開く
```

---

## 注意事項

- 文字数課金: 生成した文字数分がアカウントから差し引かれます
- レート制限: 連続リクエスト時は0.5秒のディレイを入れています
- 1リクエスト最大文字数: v3モデルは5,000字まで
