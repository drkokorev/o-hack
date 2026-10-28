"""RAG: локальный поиск по путеводителям (domains/trips/data/guides.json, собирает tools/build_guides.py).

Всё работает в процессе приложения, без сети и внешних моделей:
- лексический BM25 по основам слов (лёгкий стеммер для русского, «Будве» = «Будва»);
- смысловое сходство по векторам слов navec (входят в natasha), чтобы «где тихо и зелено» находило парки;
- фильтр по метаданным: только выбранное направление и, если понятна тема вопроса, нужный раздел статьи.
Возвращает несколько фрагментов с источником — их пересказывает LLM, а без LLM показывается сам фрагмент.
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).parent / "data" / "guides.json"
SOURCE = "Wikivoyage"
LICENSE = "CC BY-SA 4.0"

# Тема вопроса → разделы статьи, где ответ вероятнее всего
TOPIC_TAGS = {
    "visa": ("arrive",), "sights": ("see", "do"), "areas": ("areas", "sleep"), "food": ("eat", "drink"),
    "safety": ("safety",), "local_transport": ("transport",), "travel": ("arrive", "transport"),
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
    vectors: list[list[float] | None]


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


@lru_cache(maxsize=1)
def _index() -> _Index | None:
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
    return _Index(chunks, titles, stems, lengths, df, (sum(lengths) / len(lengths)) if lengths else 1.0, vectors)


def available() -> bool:
    return _index() is not None


def search(query: str, dest: str | None = None, topic: str | None = None, k: int = 3,
           min_score: float = 0.15) -> list[Snippet]:
    """Фрагменты путеводителей для вопроса; dest и topic сужают поиск (метаданные важнее сходства)."""
    index = _index()
    if index is None:
        return []
    words = tokens(query)
    q_stems = [stem(w) for w in words]
    q_vec = _vector(words)
    wanted = set(TOPIC_TAGS.get(topic or "", ()))
    n = len(index.chunks)
    scored: list[tuple[float, int]] = []
    for i, chunk in enumerate(index.chunks):
        if dest and chunk["dest"] != dest:
            continue
        if len(chunk["text"]) < 250 and chunk["text"].rstrip().endswith(":"):
            continue  # «удобно выделить следующие районы:» — сам список был таблицей и в базу не попал
        counts, length = index.stems[i], index.lengths[i]
        bm25 = 0.0
        for term in set(q_stems):
            tf = counts.get(term, 0)
            if tf:
                idf = math.log(1 + (n - index.df[term] + 0.5) / (index.df[term] + 0.5))
                bm25 += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / index.avg_len))
        vec = index.vectors[i]
        dense = sum(a * b for a, b in zip(q_vec, vec)) if q_vec and vec else 0.0
        score = min(bm25 / 8.0, 1.0) * 0.6 + max(dense, 0.0) * 0.4
        if wanted and chunk["tag"] in wanted:
            score += 0.35
        if chunk.get("order") == 0:
            score += 0.08  # первый абзац раздела обычно обзорный
        scored.append((score, i))
    scored.sort(reverse=True)
    out: list[Snippet] = []
    for score, i in scored[:k]:
        if score < min_score:
            break
        c = index.chunks[i]
        out.append(Snippet(c["dest"], c["section"], c["text"], c["url"], index.titles.get(c["dest"], c["dest"]),
                           c.get("lang", "ru"), round(float(score), 3), c.get("tag", "other")))
    return out


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
