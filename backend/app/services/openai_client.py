import json
import os

import requests

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_BASE = os.getenv("OPENAI_BASE", "https://api.openai.com/v1")
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "30"))

def extract_json_block(text: str) -> str:
    """Возвращает JSON-строку из content: ищет ```json ... ``` или первую валидную JSON-структуру."""
    t = text.strip()
    if "```" in t:
        parts = t.split("```")
        for i in range(len(parts) - 1):
            block = parts[i + 1].lstrip()
            if block.startswith("json"):
                block = block[4:].lstrip()
            block = block.split("```")[0]
            try:
                json.loads(block)
                return block
            except Exception:
                pass
    for s in (t,):
        s = s.strip()
        try:
            json.loads(s)
            return s
        except Exception:
            pass
    raise ValueError("No JSON payload found in LLM response")

def chat_completion_json(model: str, prompt: str, max_tokens: int = 400) -> str:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is empty")
    url = f"{OPENAI_BASE}/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=OPENAI_TIMEOUT)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return extract_json_block(content)
