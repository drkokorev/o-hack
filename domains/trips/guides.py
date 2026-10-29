"""RAG: локальный гибридный поиск по путеводителям (domains/trips/data/guides.json, собирает tools/build_guides.py).

Всё работает в процессе приложения, без сети и внешних сервисов:
- по словам — BM25 по основам слов (лёгкий стеммер для русского, «Будве» = «Будва»): точные совпадения
  вроде «симит», «метро», «виза»;
- по смыслу — эмбеддинги предложений multilingual-e5-small (domains/trips/embedder.py): «где тихо и зелено»
  находит абзац о парках, английский вопрос — русский абзац и наоборот. Векторы фрагментов посчитаны заранее;
  без модели запасной вариант — средние векторы слов navec из natasha;
- оценки обоих способов нормируются в пределах кандидатов и складываются пополам;
- фильтр по метаданным: только выбранное направление и, если понятна тема вопроса, нужный раздел статьи.
Возвращает несколько фрагментов с источником — их пересказывает LLM, а без LLM показывается сам фрагмент.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import threading
from collections import Counter
from dataclasses import dataclass, replace
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).parent / "data" / "guides.json"
VECTORS = Path(__file__).parent / "data" / "guides_vectors.npy"
SOURCE = "Wikivoyage"

# Тема вопроса → разделы статьи, где ответ вероятнее всего
TOPIC_TAGS = {
    "visa": ("arrive",), "sights": ("see", "do", "areas"), "areas": ("areas", "sleep"), "food": ("eat", "drink"),
    "safety": ("safety",), "local_transport": ("transport", "arrive"), "travel": ("arrive", "transport"),
    "transfer": ("arrive", "transport"), "beach": ("do", "see"), "weather": ("about",), "about": ("about",),
    "shopping": ("buy",), "nightlife": ("drink",),
}

# Раздел статьи → тег для фильтра в поиске
SECTION_TAGS = (
    (r"понять|о городе|общие сведения|история|климат|understand|climate|history", "about"),
    (r"район|districts|regions|орган", "areas"),
    (r"как добраться|прибыти|get in|въезд|виз|visa|документ|entry", "arrive"),
    (r"транспорт|передвиж|get around", "transport"),
    (r"достопримечательн|что посмотреть|посмотреть|see", "see"),
    (r"чем заняться|развлечени|пляж|отдых|do\b|beach", "do"),
    (r"покупк|шопинг|buy|деньги|money", "buy"),
    (r"еда|кухн|ресторан|eat", "eat"),
    (r"ночн|напитк|бар|drink", "drink"),
    (r"жиль|где остановиться|гостиниц|sleep", "sleep"),
    (r"безопасн|здоров|предосторожн|stay safe|stay healthy|опасност", "safety"),
    (r"связь|интернет|connect", "connect"),
    (r"поездки|окрестност|go next|day trips", "nearby"),
)


def section_tag(title: str) -> str:
    low = title.casefold()
    return next((tag for pattern, tag in SECTION_TAGS if re.search(pattern, low)), "other")


_WORD = re.compile(r"[a-zа-яё]+")
_ENDINGS = sorted((
    "иями ями ами ией иям ием ого его ому ему ыми ими ая яя ое ее ые ие ый ий ой ей ую юю ов ев ом ем ам ям ах ях "
    "ою ею ия ья ие ье ии ьи ию ью а я о е ы и у ю ь ость ости остью остей ение ения ению ением ений ениям ениями "
    "ешь ет ем ете ут ют ит им ите ат ят ал ала али ало ил ила или ило ть ться ся сь"
).split(), key=len, reverse=True)
_STOP = frozenset("и в во на с со к ко по о об от до за из у же ли не ни что как это то а но или для при так "
                  "есть быть был была было были где когда там тут здесь его ее её их он она они мы вы я".split())


def stem(word: str) -> str:
    """Очень лёгкий стеммер: отрезаем окончание, оставляя основу не короче 3 букв."""
    word = word.replace("ё", "е")
    if len(word) <= 4 or not re.match(r"[а-я]", word):
        return word
    for end in _ENDINGS:
        if word.endswith(end) and len(word) - len(end) >= 3:
            return word[: -len(end)]
    return word


def tokens(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.casefold()) if w not in _STOP and len(w) > 1]


@dataclass(frozen=True)
class Snippet:
    dest: str
    section: str
    text: str
    url: str
    title: str
    lang: str
    score: float
    tag: str = "other"

    def cite(self) -> str:
        return f"{SOURCE} «{self.title}», раздел «{self.section}»"


@dataclass
class _Index:
    chunks: list[dict]
    titles: dict[str, str]
    stems: list[Counter]
    lengths: list[int]
    df: Counter
    avg_len: float
    vectors: list[list[float] | None]          # navec — запасной вариант
    e5: "object | None" = None                 # np.ndarray [фрагменты × 384] или None


@lru_cache(maxsize=1)
def _embedding():
    try:
        from natasha import NewsEmbedding

        return NewsEmbedding()
    except Exception:  # без векторов поиск остаётся лексическим
        return None


def _vector(words: list[str]) -> list[float] | None:
    emb = _embedding()
    if emb is None:
        return None
    vecs = [emb[w] for w in words if w in emb]
    if not vecs:
        return None
    total = [sum(col) for col in zip(*vecs)]
    norm = math.sqrt(sum(x * x for x in total)) or 1.0
    return [x / norm for x in total]


_BUILD = threading.Lock()


def _index() -> _Index | None:
    # Прогрев при старте и первый запрос могут прийти одновременно — строим базу один раз
    with _BUILD:
        return _build_index()


@lru_cache(maxsize=1)
def _build_index() -> _Index | None:
    if not PATH.exists():
        return None
    data = json.loads(PATH.read_text(encoding="utf-8"))
    chunks = data.get("chunks", [])
    stems, lengths, df, vectors = [], [], Counter(), []
    seen_sections: Counter = Counter()
    for chunk in chunks:
        chunk["tag"] = section_tag(chunk["section"])  # словарь тегов мог уточниться после сборки
        chunk["order"] = seen_sections[(chunk["dest"], chunk["section"])]
        seen_sections[(chunk["dest"], chunk["section"])] += 1
        words = tokens(chunk["section"] + " " + chunk["text"])
        counts = Counter(stem(w) for w in words)
        stems.append(counts)
        lengths.append(sum(counts.values()))
        df.update(counts.keys())
        vectors.append(_vector(words))
    titles = {dest: art["title"] for dest, art in data.get("articles", {}).items()}
    index = _Index(chunks, titles, stems, lengths, df, (sum(lengths) / len(lengths)) if lengths else 1.0, vectors)
    index.e5 = _e5_matrix(data, chunks)
    return index


def passage_text(chunk: dict) -> str:
    return f"{chunk['section']}. {chunk['text']}"


def digest(texts: list[str]) -> str:
    return hashlib.sha256("\n".join(texts).encode("utf-8")).hexdigest()


def _e5_matrix(data: dict, chunks: list[dict]):
    """Готовые векторы e5, если они посчитаны для этих же фрагментов и модель доступна для вопросов."""
    from . import embedder

    if not VECTORS.exists() or not embedder.available():
        return None
    if data.get("vectors_digest") != digest([passage_text(c) for c in chunks]):
        return None  # база пересобрана, а векторы нет — не смешиваем
    import numpy as np

    matrix = np.load(VECTORS).astype(np.float32)
    return matrix if matrix.shape[0] == len(chunks) else None


def mode() -> str:
    index = _index()
    return "bm25+e5" if index is not None and index.e5 is not None else "bm25+navec"


def warm() -> None:
    """Загрузить базу, векторы и модель заранее (при старте приложения)."""
    if _index() is not None and mode() == "bm25+e5":
        from . import embedder

        embedder.encode(["прогрев"], "query")


def available() -> bool:
    return _index() is not None


def search(query: str, dest: str | None = None, topic: str | None = None, k: int = 3,
           min_score: float = 0.15, method: str | None = None) -> list[Snippet]:
    """Фрагменты путеводителей для вопроса; dest и topic сужают поиск (метаданные важнее сходства).

    method: None — лучшее доступное (bm25+e5, иначе bm25+navec); для замеров также «bm25», «e5», «navec».
    """
    index = _index()
    if index is None:
        return []
    method = method or mode()
    words = tokens(query)
    q_stems = set(stem(w) for w in words)
    wanted = set(TOPIC_TAGS.get(topic or "", ()))
    n = len(index.chunks)
    candidates = [i for i, c in enumerate(index.chunks)
                  if (not dest or c["dest"] == dest)
                  and (not wanted or c["tag"] in wanted)
                  and not (len(c["text"]) < 250 and c["text"].rstrip().endswith(":"))]
    # «удобно выделить следующие районы:» — сам список был таблицей и в базу не попал
    if not candidates:
        return []
    lexical = []
    for i in candidates:
        counts, length, bm25 = index.stems[i], index.lengths[i], 0.0
        for term in q_stems:
            tf = counts.get(term, 0)
            if tf:
                idf = math.log(1 + (n - index.df[term] + 0.5) / (index.df[term] + 0.5))
                bm25 += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / index.avg_len))
        lexical.append(bm25)
    semantic = _semantic(index, query, words, candidates, method)

    def norm(values: list[float]) -> list[float]:
        lo, hi = min(values), max(values)
        return [(v - lo) / (hi - lo) if hi > lo else (1.0 if hi > 0 else 0.0) for v in values]

    # e5 точнее средних векторов слов — ей больший вес; по словам остаются точные совпадения («симит», «виза»)
    lex_w = {"bm25": 1.0, "e5": 0.0, "navec": 0.0, "bm25+e5": 0.3}.get(method, 0.5)
    lex_n, sem_n = norm(lexical), norm(semantic) if semantic else [0.0] * len(candidates)
    scored = []
    for j, i in enumerate(candidates):
        chunk = index.chunks[i]
        score = lex_w * lex_n[j] + (1 - lex_w) * sem_n[j]
        if wanted and chunk["tag"] in wanted:
            score += 0.35
        if chunk.get("order") == 0:
            score += 0.08  # первый абзац раздела обычно обзорный
        # совсем мимо: ни одного общего слова и слабое смысловое сходство
        relevant = lexical[j] > 0 or (semantic and semantic[j] >= (0.80 if index.e5 is not None else 0.35))
        scored.append((score if relevant else score * 0.3, i))
    scored.sort(reverse=True)
    out: list[Snippet] = []
    for score, i in scored[:k]:
        if score < min_score:
            break
        c = index.chunks[i]
        out.append(Snippet(c["dest"], c["section"], c["text"], c["url"], index.titles.get(c["dest"], c["dest"]),
                           c.get("lang", "ru"), round(float(score), 3), c.get("tag", "other")))
    return out


# Generic question words do not by themselves prove that a passage answers a
# specific question. In particular, a section called "Еда" is not evidence
# that it contains information about a requested dish, diet or language.
_GENERIC_QUERY_WORDS = frozenset(stem(w) for w in tokens(
    "где куда что чем как какой какая какие какое можно ли лучше хороший хороший ли "
    "посоветуй посоветуйте расскажи расскажите скажи скажите подскажи подскажите "
    "нужен нужна стоит стоит ли есть найти поискать пойти сходить посетить посмотреть "
    "интересное интересного заняться попробовать поесть покушать перекусить пообедать "
    "поужинать завтракать обедать ужинать еда еду еды пища кухня кухню местная местной "
    "ресторан рестораны кафе заведение места место город городе районе район районов "
    "остановиться проживать жить переночевать добраться доехать попасть покататься удивить "
    "передвигаться ездить пользоваться транспорт "
    "общественный местный безопасность безопасно опасно опасность турист туристы туристам "
    "достопримечательности достопримечательность музеи музей магазин магазины покупки купить "
    "сувениры привезти домой подарок ночной жизнь вечером потанцевать клуб клубы бар бары "
    "туда здесь там тут пожалуйста хочется хочу интересно мне нам поездка поездке "
    "where what how when which is are can should does do to in at from on of for as it a the i we "
    "places place city town local good best eat food restaurant restaurants cafe cafes gift avoid "
    "see visit stay travel transport get around safety safe dangerous tourists shopping buy nightlife"
))
_QUERY_ALIASES = {
    "sushi": ("суши",), "суши": ("sushi",),
    "metro": ("метро",), "метро": ("metro",),
    "ночью": ("ночь", "ночное", "суток"),
    "pickpockets": ("карманные", "карманников"), "pickpocket": ("карманные", "карманников"),
    "недорого": ("дешево", "дешевых"), "подешевле": ("дешево", "дешевых"),
    "лыжах": ("горнолыжный", "лыжи"),
}


def _question_part(query: str) -> str:
    """Drop unrelated clauses before a question in a longer trip request."""
    parts = [part.strip() for part in re.split(r"[.!?;]+", query) if part.strip()]
    if not parts:
        return query
    part = parts[-1]
    matches = list(re.finditer(r"\b(?:где|куда|что|чем|как|where|what|how)\b", part, re.I))
    return part[matches[-1].start():] if matches else part


def _specific_words(query: str, dest: str) -> list[str]:
    from .geo import BY_ID

    place = BY_ID.get(dest)
    place_words = {stem(w) for w in tokens((place.name if place else "") + " " + dest)}
    return list(dict.fromkeys(w for w in tokens(_question_part(query))
                              if stem(w) not in _GENERIC_QUERY_WORDS and stem(w) not in place_words))


def has_specific_terms(query: str, dest: str) -> bool:
    return bool(_specific_words(query, dest))


def _one_typo(left: str, right: str) -> bool:
    """One insertion, deletion, substitution or adjacent swap; reject short words."""
    if min(len(left), len(right)) < 5 or left[:2] != right[:2] or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        differing = [i for i, (a, b) in enumerate(zip(left, right)) if a != b]
        return (len(differing) == 1 or len(differing) == 2 and differing[1] == differing[0] + 1 and
                left[differing[0]] == right[differing[1]] and left[differing[1]] == right[differing[0]])
    shorter, longer = sorted((left, right), key=len)
    i = 0
    while i < len(shorter) and shorter[i] == longer[i]:
        i += 1
    return shorter[i:] == longer[i + 1:]


def _matches_word(word: str, text: str) -> bool:
    targets = (word, *_QUERY_ALIASES.get(word, ()))
    for candidate in tokens(text):
        for target in targets:
            if stem(candidate) == stem(target):
                return True
            # A single small spelling variation is useful for names, but short
            # words and unrelated prefixes must not become asserted facts.
            if _one_typo(target, candidate):
                return True
    return False


def _evidence_window(text: str, words: list[str]) -> str | None:
    """Return one or two adjacent sentences containing every specific word."""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    for i, sentence in enumerate(sentences):
        for window in (sentence, " ".join(sentences[i:i + 2])):
            if len(window) <= 700 and all(_matches_word(word, window) for word in words):
                return window
    return None


def search_grounded(query: str, dest: str, topic: str, k: int = 4) -> list[Snippet]:
    """Retrieve topic snippets without substituting a generic answer for a specific request.

    For named items and qualifiers we require nearby text evidence. This is an
    intentionally conservative check, not proof of semantic entailment; when
    the corpus cannot substantiate a request we return no answer.
    """
    words = _specific_words(query, dest)
    # A text match alone cannot establish a dietary exclusion or medical claim.
    if topic == "food" and words and re.search(r"\b(?:без|не содержит|аллерги\w*)\b", query, re.I):
        return []
    see_first = topic == "sights" and bool(re.search(r"посмотр|посет|достопримеч|what\s+(?:to|can i)\s+see", query, re.I))
    found = search(_question_part(query), dest=dest, topic=topic, k=1000 if words or see_first else k,
                   min_score=0.0 if words else 0.15)
    if see_first:
        found.sort(key=lambda s: s.tag != "see")
    if not words:
        return found[:k]
    out = []
    for snippet in found:
        evidence = _evidence_window(snippet.text, words)
        if evidence:
            out.append(replace(snippet, text=evidence))
            if len(out) >= k:
                break
    return out


def _semantic(index: _Index, query: str, words: list[str], candidates: list[int], method: str) -> list[float]:
    if method in ("bm25+e5", "e5") and index.e5 is not None:
        from . import embedder

        q = embedder.encode([query], "query")
        if q is not None:
            return [float(x) for x in index.e5[candidates] @ q[0]]
    if method == "bm25":
        return []
    q_vec = _vector(words)
    if not q_vec:
        return []
    return [sum(a * b for a, b in zip(q_vec, vec)) if (vec := index.vectors[i]) else 0.0 for i in candidates]


def overview(dest: str) -> Snippet | None:
    """Первый абзац статьи о направлении — «о месте» для карточек идей."""
    index = _index()
    if index is None:
        return None
    for c in index.chunks:
        if c["dest"] == dest and c.get("lang") == "ru":
            return Snippet(c["dest"], c["section"], c["text"], c["url"], index.titles.get(dest, dest), "ru", 1.0,
                           c.get("tag", "about"))
    return None
