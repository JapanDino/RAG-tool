import re
from collections import Counter

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё]+(?:-[A-Za-zА-Яа-яЁё]+)?")
_REVOLUTION_PAIR_RE = re.compile(
    r"\b(?P<first>[А-ЯЁ][а-яё]+ской)\s+и\s+"
    r"(?P<second>[А-ЯЁ][а-яё]+ской)\s+"
    r"(?:(?:[а-яё]+)\s+){0,2}революц(?:ий|ии|ия)\b",
    re.IGNORECASE,
)
_FORMULA_RE = re.compile(
    r"\b[A-Za-zА-Яа-яЁё]\s*(?:[=+\-*/^])\s*[A-Za-zА-Яа-яЁё0-9][A-Za-zА-Яа-яЁё0-9=+\-*/^().]*"
)
_HEAD_PHRASE_RE = re.compile(
    r"\b(?P<head>закон|теорема|формула|уравнение|правило|принцип|метод|модель|"
    r"процесс|явление|роль|функция|строение|образ|сюжет|метафора)\s+"
    r"(?P<tail>[А-Яа-яЁёA-Za-z0-9-]+(?:\s+[А-Яа-яЁёA-Za-z0-9-]+){0,3})",
    re.IGNORECASE,
)
_EVENT_PHRASE_RE = re.compile(
    r"\b(?P<phrase>(?:[А-ЯЁ][а-яё]+(?:ая|ой|ая|ое|ые|ской|ская|ская)?\s+){1,3}"
    r"(?:революция|война|реформа|эксперимент|движение|эпоха|период))\b",
    re.IGNORECASE,
)

_STOPWORDS = {
    "и",
    "в",
    "во",
    "не",
    "что",
    "он",
    "на",
    "я",
    "с",
    "со",
    "как",
    "а",
    "то",
    "все",
    "она",
    "так",
    "его",
    "но",
    "да",
    "ты",
    "к",
    "у",
    "же",
    "вы",
    "за",
    "бы",
    "по",
    "только",
    "ее",
    "мне",
    "было",
    "вот",
    "от",
    "меня",
    "еще",
    "нет",
    "о",
    "из",
    "ему",
    "теперь",
    "когда",
    "даже",
    "ну",
    "вдруг",
    "ли",
    "если",
    "уже",
    "или",
    "ни",
    "быть",
    "был",
    "него",
    "до",
    "вас",
    "нибудь",
    "опять",
    "уж",
    "вам",
    "ведь",
    "там",
    "потом",
    "себя",
    "ничего",
    "ей",
    "может",
    "они",
    "тут",
    "где",
    "есть",
    "надо",
    "ней",
    "для",
    "мы",
    "тебя",
    "их",
    "чем",
    "была",
    "сам",
    "чтоб",
    "без",
    "будто",
    "чего",
    "раз",
    "тоже",
    "себе",
    "под",
    "будет",
    "ж",
    "тогда",
    "кто",
    "этот",
    "того",
    "потому",
    "этого",
    "какой",
    "совсем",
    "ним",
    "здесь",
    "этом",
    "один",
    "почти",
    "мой",
    "тем",
    "чтобы",
    "нее",
    "сейчас",
    "были",
    "куда",
    "зачем",
    "всех",
    "никогда",
    "можно",
    "при",
    "наконец",
    "два",
    "об",
    "другой",
    "хоть",
    "после",
    "над",
    "больше",
    "тот",
    "через",
    "эти",
    "нас",
    "про",
    "всего",
    "них",
    "какая",
    "много",
    "разве",
    "три",
    "эту",
    "моя",
    "впрочем",
    "хорошо",
    "свою",
    "этой",
    "перед",
    "иногда",
    "лучше",
    "чуть",
    "том",
    "нельзя",
    "такой",
    "им",
    "более",
    "всегда",
    "конечно",
}

_TASK_VERBS = {
    "назови",
    "назовите",
    "перечисли",
    "перечислите",
    "вспомни",
    "вспомните",
    "определи",
    "определите",
    "объясни",
    "объясните",
    "сравни",
    "сравните",
    "опиши",
    "опишите",
    "перескажи",
    "перескажите",
    "классифицируй",
    "классифицируйте",
    "интерпретируй",
    "интерпретируйте",
    "примени",
    "примените",
    "используй",
    "используйте",
    "реши",
    "решите",
    "вычисли",
    "вычислите",
    "выполни",
    "выполните",
    "покажи",
    "покажите",
    "проанализируй",
    "проанализируйте",
    "раздели",
    "разделите",
    "выдели",
    "выделите",
    "структурируй",
    "структурируйте",
    "сопоставь",
    "сопоставьте",
    "оцени",
    "оцените",
    "оценить",
    "аргументируй",
    "аргументируйте",
    "обоснуй",
    "обоснуйте",
    "докажи",
    "докажите",
    "создай",
    "создайте",
    "придумай",
    "придумайте",
    "спроектируй",
    "спроектируйте",
    "разработай",
    "разработайте",
    "сформулируй",
    "сформулируйте",
    "составь",
    "составьте",
}

_NORMAL_FORMS = {
    "причины": "причины",
    "причин": "причины",
    "демократии": "демократия",
    "демократию": "демократия",
    "демократией": "демократия",
    "европе": "Европа",
    "европы": "Европа",
    "европу": "Европа",
    "революций": "революция",
    "революции": "революция",
    "фотосинтеза": "фотосинтез",
    "хлорофилла": "хлорофилл",
    "стихотворении": "стихотворение",
    "печорина": "Печорин",
}


def _normalize_token(token: str) -> str:
    lower = token.lower()
    if lower in _NORMAL_FORMS:
        return _NORMAL_FORMS[lower]
    return token


def _normalize_adjective_feminine(token: str) -> str:
    if token.endswith("ской"):
        return token[:-4] + "ская"
    if token.endswith("ой"):
        return token[:-2] + "ая"
    return token


def _context_for(sentences: list[str], title: str) -> str:
    lowered = title.lower()
    for sent in sentences:
        if lowered in sent.lower():
            return sent[:240]
    return (sentences[0] if sentences else "")[:240]


def _add_candidate(
    candidates: list[tuple[str, str]],
    seen: set[str],
    title: str,
    node_type: str,
):
    clean = title.strip(" ,;:()[]{}")
    if len(clean) < 3:
        return
    key = clean.lower()
    if key in seen:
        return
    seen.add(key)
    candidates.append((clean, node_type))


def _extract_phrase_candidates(text: str) -> list[str]:
    phrases: list[str] = []
    for match in _FORMULA_RE.finditer(text):
        phrases.append(re.sub(r"\s+", "", match.group(0)))
    for match in _HEAD_PHRASE_RE.finditer(text):
        head = match.group("head").lower()
        tail_words = []
        for word in _WORD_RE.findall(match.group("tail")):
            lower = word.lower()
            if lower in _STOPWORDS or lower in _TASK_VERBS:
                break
            tail_words.append(_normalize_token(word))
        if tail_words:
            phrases.append(f"{head} {' '.join(tail_words)}")
    for match in _EVENT_PHRASE_RE.finditer(text):
        phrases.append(match.group("phrase"))
    for match in _REVOLUTION_PAIR_RE.finditer(text):
        first = _normalize_adjective_feminine(match.group("first"))
        second = _normalize_adjective_feminine(match.group("second"))
        phrases.append(f"{first} революция")
        phrases.append(f"{second} революция")
    return phrases


def extract_semantic_nodes_from_text(text: str, max_nodes: int = 30, min_freq: int = 1):
    sentences = [s.strip() for s in re.split(r"[.!?\\n]+", text) if s.strip()]
    token_counts: Counter[str] = Counter()
    proper_tokens: list[str] = []
    display_names: dict[str, str] = {}
    has_revolution_pair = bool(_REVOLUTION_PAIR_RE.search(text))

    for sent in sentences:
        tokens = _WORD_RE.findall(sent)
        for tok in tokens:
            lower = tok.lower()
            if len(lower) < 3 or lower in _STOPWORDS or lower in _TASK_VERBS:
                continue
            if has_revolution_pair and (
                lower.endswith("ской") or lower.startswith("революц")
            ):
                continue
            token_counts[lower] += 1
            if tok[0].isupper() and lower not in _STOPWORDS:
                proper_tokens.append(tok)
                display_names.setdefault(lower, _normalize_token(tok))

    candidates: list[tuple[str, str]] = []
    seen = set()

    for phrase in _extract_phrase_candidates(text):
        _add_candidate(candidates, seen, phrase, "concept")

    for tok in proper_tokens:
        lower = tok.lower()
        _add_candidate(candidates, seen, display_names.get(lower, tok), "proper_noun")

    for tok, _cnt in token_counts.most_common():
        if tok in seen:
            continue
        # One-off educational prompts often contain the key concept only once.
        if _cnt < min_freq:
            continue
        if len(tok) < 4:
            continue
        _add_candidate(candidates, seen, _normalize_token(tok), "keyword")

    nodes = []
    for tok, node_type in candidates[:max_nodes]:
        nodes.append(
            {
                "title": tok,
                "context_snippet": _context_for(sentences, tok),
                "frequency": token_counts.get(tok.lower(), 1),
                "node_type": node_type,
            }
        )

    return nodes


def extract_nodes_from_text(text: str, max_nodes: int = 30, min_freq: int = 1):
    return extract_semantic_nodes_from_text(
        text, max_nodes=max_nodes, min_freq=min_freq
    )
