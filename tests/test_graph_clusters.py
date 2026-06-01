"""Unit tests for the graph clustering Union-Find algorithm.

These tests do not require a running database — they exercise the pure
algorithmic core (_DSU) imported from the router module.
"""
from __future__ import annotations

import pytest


def test_dsu_singleton_clusters():
    from backend.app.routers.graph import _DSU
    dsu = _DSU([1, 2, 3, 4, 5])
    roots = {dsu.find(i) for i in [1, 2, 3, 4, 5]}
    assert len(roots) == 5, "Without unions every node is its own cluster"


def test_dsu_chain_union():
    from backend.app.routers.graph import _DSU
    dsu = _DSU([1, 2, 3, 4])
    dsu.union(1, 2)
    dsu.union(2, 3)
    # 1-2-3 merged, 4 separate
    assert dsu.find(1) == dsu.find(2) == dsu.find(3)
    assert dsu.find(4) != dsu.find(1)
    assert dsu.size[dsu.find(1)] == 3


def test_dsu_two_components():
    from backend.app.routers.graph import _DSU
    ids = list(range(10))
    dsu = _DSU(ids)
    # component A: 0-1-2-3
    for a, b in [(0, 1), (1, 2), (2, 3)]:
        dsu.union(a, b)
    # component B: 4-5-6
    for a, b in [(4, 5), (5, 6)]:
        dsu.union(a, b)
    # 7, 8, 9 stay isolated
    roots = {dsu.find(i) for i in ids}
    assert len(roots) == 5  # 2 multi-node + 3 singleton


def test_dsu_redundant_union_is_safe():
    from backend.app.routers.graph import _DSU
    dsu = _DSU([1, 2])
    dsu.union(1, 2)
    dsu.union(1, 2)  # idempotent
    dsu.union(2, 1)  # symmetric
    assert dsu.find(1) == dsu.find(2)
    assert dsu.size[dsu.find(1)] == 2


def test_dsu_handles_path_compression():
    """Long chain should still resolve in roughly O(1) after compression."""
    from backend.app.routers.graph import _DSU
    n = 100
    dsu = _DSU(list(range(n)))
    for i in range(n - 1):
        dsu.union(i, i + 1)
    root = dsu.find(0)
    for i in range(n):
        assert dsu.find(i) == root


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
