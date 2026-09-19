"""Cancelable provider streaming and bounded parsing of a draft JSON answer."""

import json
import os

import httpx


async def stream_completion(prompt: str):
    key = os.environ["OPENAI_API_KEY"]
    model = os.getenv("LLM_MODEL", "deepseek-v4-flash")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
        "max_tokens": 3000,
        "stream": True,
    }
    url = (
        os.getenv("OPENAI_BASE", "https://api.openai.com/v1").rstrip("/")
        + "/chat/completions"
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as client:  # noqa: SIM117 - Response lifetime is nested inside the HTTP client.
        async with client.stream(
            "POST", url, headers={"Authorization": "Bearer " + key}, json=payload
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                if event.get("error"):
                    raise ValueError("Provider stream failed")
                choices = event.get("choices", [])
                if choices:
                    content = choices[0].get("delta", {}).get("content")
                    if isinstance(content, str):
                        yield content


def draft_answer(raw: str, allowed: set[int]) -> str:
    """Only expose answer text after a complete, valid top-level citations array."""
    decoder = json.JSONDecoder()
    start = raw.find("{")
    if start < 0 or start > 12:
        return ""
    cursor, fields = start + 1, {}
    while cursor < len(raw):
        try:
            while raw[cursor].isspace() or raw[cursor] == ",":
                cursor += 1
            key, cursor = decoder.raw_decode(raw, cursor)
            while raw[cursor].isspace():
                cursor += 1
            if raw[cursor] != ":":
                return ""
            cursor += 1
            while raw[cursor].isspace():
                cursor += 1
            try:
                value, cursor = decoder.raw_decode(raw, cursor)
                fields[key] = value
            except json.JSONDecodeError:
                if key == "answer" and raw[cursor] == '"':
                    fragment = raw[cursor + 1 :]
                    for trim in range(min(12, len(fragment) + 1)):
                        try:
                            value = json.loads(
                                '"' + (fragment[:-trim] if trim else fragment) + '"'
                            )
                            if any(0xD800 <= ord(char) <= 0xDFFF for char in value):
                                continue
                            fields[key] = value
                            break
                        except json.JSONDecodeError:
                            continue
                break
        except (json.JSONDecodeError, IndexError, TypeError):
            break
    ids = fields.get("citations")
    answer = fields.get("answer")
    if (
        isinstance(ids, list)
        and ids
        and all(type(i) is int and i in allowed for i in ids)
        and isinstance(answer, str)
    ):
        return answer[:12000]
    return ""
