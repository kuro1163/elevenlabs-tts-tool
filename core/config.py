"""設定ファイル (config.json) の読み書き"""
import json
import os

# プロジェクトルート（core/ の1つ上）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_config(config_path: str = None) -> dict:
    """config.json を読み込む。config_path 省略時はプロジェクトルートの config.json。"""
    if config_path is None:
        config_path = os.path.join(BASE_DIR, "config.json")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(config: dict, config_path: str = None):
    """config.json を保存する。"""
    if config_path is None:
        config_path = os.path.join(BASE_DIR, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)
