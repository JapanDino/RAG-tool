import json
from pathlib import Path

from backend.app.utils.bloom import classify_bloom_multilabel
from backend.app.utils.node_extract import extract_nodes_from_text


def _demo_module():
    path = Path(__file__).resolve().parents[1] / "data" / "demo_knowledge_module.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_demo_module_expected_nodes_and_levels():
    demo = _demo_module()

    nodes = extract_nodes_from_text(demo["text"], max_nodes=30, min_freq=1)
    titles = {node["title"] for node in nodes}
    classification = classify_bloom_multilabel(demo["text"], min_prob=0.2, max_levels=4)

    assert {"закон сохранения энергии", "F=ma"}.issubset(titles)
    assert {"массы", "ускорение"}.intersection(titles)
    assert set(demo["expected_levels"]).issubset(set(classification["top_levels"]))


def test_demo_module_expected_graph_fixture_is_well_formed():
    demo = _demo_module()
    expected_nodes = set(demo["expected_nodes"])

    assert demo["expected_edges"]
    for edge in demo["expected_edges"]:
        assert edge["from"] in expected_nodes
        assert edge["to"] in expected_nodes
        assert edge["method"] == "semantic_or_co_occurrence"
