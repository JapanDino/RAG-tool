from backend.app.services.node_extractor import get_node_extractor
from backend.app.utils.bloom import classify_bloom_multilabel
from backend.app.utils.node_extract import extract_nodes_from_text

TZ_EXAMPLE = (
    "Сравните причины Французской и Английской буржуазных революций, "
    "чтобы оценить их влияние на становление демократии в Европе"
)


def test_tz_example_extracts_meaningful_nodes():
    nodes = extract_nodes_from_text(TZ_EXAMPLE, max_nodes=30, min_freq=1)
    titles = {node["title"] for node in nodes}

    assert "Сравните" not in titles
    assert "Французская революция" in titles
    assert "Английская революция" in titles
    assert "причины" in titles
    assert "демократия" in titles
    assert "Европа" in titles


def test_tz_example_prioritizes_analysis_and_evaluation():
    result = classify_bloom_multilabel(TZ_EXAMPLE, min_prob=0.2, max_levels=2)

    assert result["top_levels"] == ["analyze", "evaluate"]
    assert result["prob_vector"][3] >= 0.2
    assert result["prob_vector"][4] >= 0.2
    assert result["triggers"]["analyze"]
    assert result["triggers"]["evaluate"]


def test_default_node_extractor_is_semantic(monkeypatch):
    monkeypatch.delenv("NODE_EXTRACTOR", raising=False)
    get_node_extractor.cache_clear()

    try:
        extractor = get_node_extractor()
        nodes = extractor.extract(TZ_EXAMPLE, max_nodes=30, min_freq=1)
    finally:
        get_node_extractor.cache_clear()

    assert extractor.name == "semantic"
    assert {node["title"] for node in nodes} >= {
        "Французская революция",
        "Английская революция",
        "причины",
        "демократия",
        "Европа",
    }


def test_semantic_extractor_handles_multiple_subjects():
    examples = [
        (
            "Проанализируйте причины промышленной революции и ее последствия для городов.",
            {"промышленной революции", "причины"},
        ),
        (
            "Объясните роль хлорофилла в процессе фотосинтеза.",
            {"роль хлорофилл", "фотосинтез"},
        ),
        (
            "Используйте формулу F=ma для решения задачи о силе.",
            {"F=ma", "формула F"},
        ),
        (
            "Оцените образ Печорина и метафору дороги в стихотворении.",
            {"образ Печорин", "метафора дороги"},
        ),
    ]

    for text, expected in examples:
        titles = {
            node["title"]
            for node in extract_nodes_from_text(text, max_nodes=30, min_freq=1)
        }
        assert not titles.intersection(
            {"Проанализируйте", "Объясните", "Используйте", "Оцените"}
        )
        assert expected.intersection(titles), (text, titles)
