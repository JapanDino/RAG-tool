import json
import os

import requests

_DEFAULT_BASE = "https://api.openai.com/v1"
OPENAI_TIMEOUT = float(os.getenv("OPENAI_TIMEOUT", "30"))


def _base() -> str:
    return os.getenv("OPENAI_BASE", _DEFAULT_BASE).rstrip("/")

def extract_json_block(text: str) -> str:
    """Возвращает JSON-строку из content: ищет ```json ... ``` или первую валидную JSON-структуру."""
    import re as _re
    # Strip Qwen3 chain-of-thought tags
    t = _re.sub(r"<think>.*?</think>", "", text, flags=_re.DOTALL).strip()
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
    # Try whole text
    try:
        json.loads(t)
        return t
    except Exception:
        pass
    # Try to find first {...} block
    start = t.find("{")
    end = t.rfind("}")
    if start != -1 and end > start:
        candidate = t[start:end + 1]
        try:
            json.loads(candidate)
            return candidate
        except Exception:
            pass
    raise ValueError("No JSON payload found in LLM response")

def chat_completion_json(model: str, prompt: str, max_tokens: int = 400) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is empty")
    url = f"{_base()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # /no_think disables Qwen3 chain-of-thought to avoid multi-minute delays
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "/no_think\n" + prompt}],
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=OPENAI_TIMEOUT)
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return extract_json_block(content)


def chat_completion_stream(
    model: str,
    messages: list[dict],
    max_tokens: int = 1024,
):
    """Yields text chunks from a streaming chat completion."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is empty")
    url = f"{_base()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": max_tokens,
        "stream": True,
    }
    with requests.post(url, headers=headers, json=payload, stream=True, timeout=OPENAI_TIMEOUT) as resp:
        resp.raise_for_status()
        for raw_line in resp.iter_lines():
            if not raw_line:
                continue
            line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
            if line.startswith("data: "):
                data = line[6:]
                if data.strip() == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                    delta = chunk["choices"][0].get("delta", {})
                    text = delta.get("content") or ""
                    if text:
                        yield text
                except Exception:
                    continue


def embeddings(model: str, inputs: list[str]) -> list[list[float]]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is empty")
    url = f"{_base()}/embeddings"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "input": inputs,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=OPENAI_TIMEOUT)
    resp.raise_for_status()
    data = resp.json()["data"]
    # Preserve input order.
    data_sorted = sorted(data, key=lambda x: x["index"])
    return [item["embedding"] for item in data_sorted]
