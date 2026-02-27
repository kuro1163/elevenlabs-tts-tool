# ElevenLabs TTS Generator

キャラ名とセリフをコピペ → 自動でキャラごとのvoice_idに紐づけ → ElevenLabs APIで音声生成するツール

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

## 注意事項

- 文字数課金: 生成した文字数分がアカウントから差し引かれます
- レート制限: 連続リクエスト時は0.5秒のディレイを入れています
- 1リクエスト最大文字数: v3モデルは5,000字まで
