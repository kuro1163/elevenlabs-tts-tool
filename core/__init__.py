"""
core パッケージ: ビジネスロジック（GUI非依存）
"""
from core.config import BASE_DIR, load_config, save_config
from core.client import get_client
from core.csv_io import read_csv_rows, check_csv_alignment

__all__ = [
    'BASE_DIR', 'load_config', 'save_config',
    'get_client',
    'read_csv_rows', 'check_csv_alignment',
]
