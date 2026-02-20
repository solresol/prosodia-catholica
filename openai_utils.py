from __future__ import annotations

import os
from pathlib import Path


def load_openai_api_key() -> str:
    env_key = os.environ.get("OPENAI_API_KEY")
    if env_key:
        return env_key.strip()

    key_path = Path.home() / ".openai.key"
    if not key_path.exists():
        raise FileNotFoundError(
            f"OpenAI API key file not found: {key_path} (or set OPENAI_API_KEY)"
        )
    return key_path.read_text(encoding="utf-8").strip()

