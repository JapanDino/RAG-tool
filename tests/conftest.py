import sys
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure():
    # Keep unit tests lightweight and deterministic.
    os.environ.setdefault("EMBEDDING_PROVIDER", "random")
    os.environ.setdefault("NODE_EXTRACTOR", "heuristic")
    os.environ.setdefault("BLOOM_CLASSIFIER", "keyword")
