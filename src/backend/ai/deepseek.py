import os

from src.backend.services.settings import load_settings

_deepseek_client = None


def get_deepseek_client():
    global _deepseek_client
    if _deepseek_client is None:
        from openai import OpenAI

        s = load_settings()
        api_key = (s.get("deepseek") or {}).get("api_key", "") or os.getenv("DEEPSEEK_API_KEY", "")
        _deepseek_client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    return _deepseek_client

def reset_deepseek_client():
    global _deepseek_client
    _deepseek_client = None
