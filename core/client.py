"""ElevenLabs APIクライアント初期化"""
import os

from core.config import BASE_DIR


def get_client():
    """dotenv 読込 + ElevenLabs クライアント初期化。APIキーなしは RuntimeError。"""
    from dotenv import load_dotenv
    from elevenlabs.client import ElevenLabs

    load_dotenv(os.path.join(BASE_DIR, ".env"))
    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("ELEVENLABS_API_KEY が .env に設定されていません")
    return ElevenLabs(api_key=api_key)
