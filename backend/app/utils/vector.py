from typing import Iterable, List

def vector_literal(vec: Iterable[float]) -> str:
    """
    Возвращает строку вида '[0.1, -0.2, ...]' для подстановки в SQL как :qvec::vector.
    Предполагается безопасная подстановка через bind-параметры в текстовом виде.
    """
    # округлим до 6 знаков чтобы не раздуть запрос
    parts = [("{:.6f}".format(float(v))).rstrip('0').rstrip('.') if '.' in "{:.6f}".format(float(v)) else "{:.6f}".format(float(v)) for v in vec]
    return "[" + ", ".join(parts) + "]"
