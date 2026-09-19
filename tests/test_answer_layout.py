from backend.app.services.answer_layout import validated_layout


def test_layout_requires_cited_evidence_and_valid_graph():
    section = {"heading": "Объяснение", "body": "Связь двух фаз", "citations": [2]}
    diagram = {
        "title": "Связь",
        "nodes": [{"id": "a", "label": "Свет"}, {"id": "b", "label": "АТФ"}],
        "edges": [{"source": "a", "target": "b", "label": "энергия"}],
        "citations": [2],
    }
    answer = {"sections": [section], "diagram": diagram}
    assert validated_layout(answer, [2])["diagram"] == diagram
    assert validated_layout(answer, [1]) == {"sections": [], "diagram": None}
    diagram["edges"][0]["target"] = "unknown"
    result = validated_layout(answer, [2])
    assert result["sections"] and result["diagram"] is None
    diagram["edges"][0]["target"] = "b"
    diagram["nodes"][1]["id"] = "a"
    assert validated_layout(answer, [2])["diagram"] is None


def test_malformed_or_unbounded_layout_keeps_plain_answer_usable():
    assert validated_layout({"sections": "invalid", "diagram": "<svg/>"}, [1]) == {
        "sections": [],
        "diagram": None,
    }
    section = {"heading": "x", "body": "x", "citations": [1]}
    assert not validated_layout({"sections": [section] * 5}, [1])["sections"]
    section["citations"] = [True]
    assert not validated_layout({"sections": [section]}, [1])["sections"]
