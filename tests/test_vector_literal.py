from backend.app.utils.vector import vector_literal
def test_vector_literal():
    s = vector_literal([0.1, -0.2, 1.0])
    assert s.startswith('[') and s.endswith(']')
    assert ',' in s
