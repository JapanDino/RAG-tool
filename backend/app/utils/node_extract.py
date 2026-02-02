import re
from collections import Counter

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)?")

_STOPWORDS = {
    "и","в","во","не","что","он","на","я","с","со","как","а","то","все","она","так","его","но",
    "да","ты","к","у","же","вы","за","бы","по","только","ее","мне","было","вот","от","меня",
    "еще","нет","о","из","ему","теперь","когда","даже","ну","вдруг","ли","если","уже","или",
    "ни","быть","был","него","до","вас","нибудь","опять","уж","вам","ведь","там","потом","себя",
    "ничего","ей","может","они","тут","где","есть","надо","ней","для","мы","тебя","их","чем",
    "была","сам","чтоб","без","будто","чего","раз","тоже","себе","под","будет","ж","тогда",
    "кто","этот","того","потому","этого","какой","совсем","ним","здесь","этом","один","почти",
    "мой","тем","чтобы","нее","сейчас","были","куда","зачем","всех","никогда","можно","при",
    "наконец","два","об","другой","хоть","после","над","больше","тот","через","эти","нас",
    "про","всего","них","какая","много","разве","три","эту","моя","впрочем","хорошо","свою",
    "этой","перед","иногда","лучше","чуть","том","нельзя","такой","им","более","всегда","конечно",
}

def extract_nodes_from_text(text: str, max_nodes: int = 30, min_freq: int = 1):
    sentences = [s.strip() for s in re.split(r"[.!?\\n]+", text) if s.strip()]
    token_counts: Counter[str] = Counter()
    proper_tokens: list[str] = []
    display_names: dict[str, str] = {}

    for sent in sentences:
        tokens = _WORD_RE.findall(sent)
        for tok in tokens:
            lower = tok.lower()
            if len(lower) < 3 or lower in _STOPWORDS:
                continue
            token_counts[lower] += 1
            if tok[0].isupper() and lower not in _STOPWORDS:
                proper_tokens.append(tok)
                display_names.setdefault(lower, tok)

    candidates: list[tuple[str, str]] = []
    seen = set()

    for tok in proper_tokens:
        lower = tok.lower()
        if lower in seen:
            continue
        seen.add(lower)
        candidates.append((lower, "proper_noun"))

    for tok, _cnt in token_counts.most_common():
        if tok in seen:
            continue
        if _cnt < min_freq:
            continue
        seen.add(tok)
        candidates.append((tok, "keyword"))

    nodes = []
    for tok, node_type in candidates[:max_nodes]:
        context = ""
        for sent in sentences:
            if re.search(rf"\\b{re.escape(tok)}\\b", sent, flags=re.IGNORECASE):
                context = sent
                break
        nodes.append({
            "title": display_names.get(tok, tok),
            "context_snippet": context[:240],
            "frequency": token_counts.get(tok, 1),
            "node_type": node_type,
        })

    return nodes
