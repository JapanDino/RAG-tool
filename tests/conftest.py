import os


def pytest_configure():
    # Keep unit tests lightweight and deterministic.
    os.environ.setdefault("EMBEDDING_PROVIDER", "random")
    os.environ.setdefault("NODE_EXTRACTOR", "heuristic")
    os.environ.setdefault("BLOOM_CLASSIFIER", "keyword")

