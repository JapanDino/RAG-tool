from backend.app.services.openai_client import extract_json_block


def test_extract_json_from_fence():
    content = """Here is JSON:
```json
{"a":1,"b":2}
```"""
    assert extract_json_block(content).strip().startswith("{")
