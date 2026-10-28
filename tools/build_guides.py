"""База знаний для RAG: путеводители Wikivoyage по направлениям каталога, нарезанные по разделам.

    .venv/bin/python -m tools.build_guides            # докачать недостающие направления
    .venv/bin/python -m tools.build_guides --force    # перекачать всё

Берём статью ru.wikivoyage.org (если её нет — en.wikivoyage.org) в виде HTML, раскладываем по разделам
(«Достопримечательности», «Районы», «Транспорт», «Въезд»…) и режем на куски ~700 символов. У каждого куска —
направление, раздел, ссылка и номер версии статьи. Лицензия текстов — CC BY-SA, источник подписывается в ответе.
Результат: domains/trips/data/guides.json; поиск по нему работает локально (domains/trips/guides.py).
"""

from __future__ import annotations

import argparse
import json
import re
import time
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from domains.trips.geo import DESTINATIONS
from domains.trips.guides import section_tag

OUT = Path(__file__).resolve().parent.parent / "domains" / "trips" / "data" / "guides.json"
UA = {"User-Agent": "o-odin-zapros/1.0 (hackathon prototype; github.com/ostrovok-hackathon-2026)"}
CHUNK = 700
MAX_CHUNKS = 90  # на статью: крупные города не должны вытеснять остальные

# Статья, если она называется иначе, чем направление каталога; затем английская на запас
TITLES_RU = {"baikal": "Иркутск", "murmansk": "Мурманск", "sanya": "Санья", "cyprus": "Айя-Напа",
             "altai": "Республика Алтай", "kamchatka": "Петропавловск-Камчатский", "tunisia": "Хаммамет",
             "srilanka": "Шри-Ланка", "maldives": "Мальдивы", "dagestan": "Дагестан", "karelia": "Карелия"}
TITLES_EN = {"sochi": "Sochi", "kaliningrad": "Kaliningrad", "kazan": "Kazan", "spb": "Saint Petersburg",
             "moscow": "Moscow", "kislovodsk": "Kislovodsk", "altai": "Altai Republic", "baikal": "Irkutsk",
             "murmansk": "Murmansk", "dagestan": "Dagestan", "vladivostok": "Vladivostok", "kamchatka": "Kamchatka Krai",
             "sheregesh": "Sheregesh", "karelia": "Republic of Karelia", "nnovgorod": "Nizhny Novgorod",
             "antalya": "Antalya", "istanbul": "Istanbul", "dubai": "Dubai", "hurghada": "Hurghada",
             "sharm": "Sharm el-Sheikh", "phuket": "Phuket", "nhatrang": "Nha Trang", "sanya": "Sanya",
             "maldives": "Maldives", "srilanka": "Sri Lanka", "tbilisi": "Tbilisi", "batumi": "Batumi",
             "yerevan": "Yerevan", "samarkand": "Samarkand", "baku": "Baku", "minsk": "Minsk", "almaty": "Almaty",
             "bali": "Bali", "goa": "Goa", "budva": "Budva", "cyprus": "Ayia Napa", "crete": "Crete", "rome": "Rome",
             "barcelona": "Barcelona", "paris": "Paris", "lisbon": "Lisbon", "prague": "Prague",
             "budapest": "Budapest", "belgrade": "Belgrade", "dubrovnik": "Dubrovnik", "durres": "Durrës",
             "tokyo": "Tokyo", "seoul": "Seoul", "bangkok": "Bangkok", "phuquoc": "Phu Quoc", "beijing": "Beijing",
             "kualalumpur": "Kuala Lumpur", "singapore": "Singapore", "doha": "Doha", "muscat": "Muscat",
             "aqaba": "Aqaba", "marrakech": "Marrakech", "tunisia": "Hammamet", "zanzibar": "Zanzibar",
             "seychelles": "Seychelles", "mauritius": "Mauritius", "newyork": "New York City", "miami": "Miami",
             "losangeles": "Los Angeles", "cancun": "Cancún", "varadero": "Varadero", "puntacana": "Punta Cana",
             "rio": "Rio de Janeiro", "buenosaires": "Buenos Aires", "yaroslavl": "Yaroslavl",
             "yekaterinburg": "Yekaterinburg", "samara": "Samara", "ufa": "Ufa", "perm": "Perm", "tyumen": "Tyumen"}

SKIP_SECTIONS = re.compile(r"примечани|ссылк|литератур|see also|references|external", re.IGNORECASE)


class _Text(HTMLParser):
    """HTML статьи → [(раздел, абзац)]: заголовки h2/h3 задают раздел, текст берём из p/li/dd."""

    BLOCKS = {"p", "li", "dd"}
    SKIP = {"style", "script", "sup", "table", "figure", "math"}
    VOID = {"img", "br", "hr", "meta", "link", "input", "wbr", "source", "col", "area"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.section, self.out, self.buf = "Вступление", [], []
        self.h2 = "Вступление"
        self.heading = None
        self.stack: list[tuple[str, bool]] = []  # (тег, пропускаем ли его содержимое)

    @property
    def skipping(self) -> bool:
        return any(skip for _, skip in self.stack)

    def handle_starttag(self, tag, attrs):
        if tag in self.VOID:
            return
        cls = dict(attrs).get("class") or ""
        self.stack.append((tag, tag in self.SKIP or "noprint" in cls.split() or "mw-editsection" in cls))
        if tag in ("h2", "h3"):
            self.heading = []

    def handle_endtag(self, tag):
        if tag in self.VOID or not any(t == tag for t, _ in self.stack):
            return
        while self.stack:
            top, _ = self.stack.pop()
            if top == tag:
                break
        if tag in ("h2", "h3") and self.heading is not None:
            title, self.heading = " ".join("".join(self.heading).split()), None
            # Подраздел наследует раздел: «Достопримечательности — Старый город» → тег see
            self.h2 = title if tag == "h2" else self.h2
            self.section = title if tag == "h2" else f"{self.h2} — {title}"
        elif tag in self.BLOCKS and not any(t in self.BLOCKS for t, _ in self.stack):
            text = " ".join("".join(self.buf).split())
            self.buf = []
            if len(text) > 40:
                self.out.append((self.section, text))

    def handle_data(self, data):
        if self.skipping:
            return
        if self.heading is not None:
            self.heading.append(data)
        elif any(t in self.BLOCKS for t, _ in self.stack):
            self.buf.append(data)


def fetch_json(url: str) -> dict:
    for attempt in range(5):
        try:
            with urlopen(Request(url, headers=UA), timeout=60) as resp:
                return json.loads(resp.read())
        except Exception as err:  # 429, обрыв, DNS — пауза и повтор
            if attempt == 4:
                raise
            print(f"  {type(err).__name__}, повтор через {5 * (attempt + 1)} с")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError("недостижимо")


def article(lang: str, title: str) -> dict | None:
    params = {"action": "parse", "format": "json", "page": title, "prop": "text|revid|displaytitle",
              "redirects": 1, "disableeditsection": 1, "disabletoc": 1}
    data = fetch_json(f"https://{lang}.wikivoyage.org/w/api.php?{urlencode(params)}")
    if "error" in data:
        return None
    parse = data["parse"]
    parser = _Text()
    parser.feed(parse["text"]["*"])
    return {"title": parse["title"], "revid": parse["revid"], "lang": lang, "paragraphs": parser.out,
            "url": f"https://{lang}.wikivoyage.org/wiki/{quote(parse['title'].replace(' ', '_'))}"}


def chunks(dest_id: str, art: dict) -> list[dict]:
    out: list[dict] = []
    by_section: dict[str, list[str]] = {}
    for section, text in art["paragraphs"]:
        if not SKIP_SECTIONS.search(section):
            by_section.setdefault(section, []).append(re.sub(r"\[\d+\]", "", text))
    for section, paragraphs in by_section.items():
        texts, buf = [], ""
        for para in paragraphs:
            para = para[:CHUNK]
            if buf and len(buf) + len(para) > CHUNK:
                texts.append(buf)
                buf = ""
            buf = (buf + " " + para).strip()
        if buf:
            texts.append(buf)
        out += [{"dest": dest_id, "section": section, "tag": section_tag(section), "text": text,
                 "lang": art["lang"], "url": art["url"]} for text in texts]
    return out[:MAX_CHUNKS]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--vectors", action="store_true", help="только пересчитать векторы e5 для готовых фрагментов")
    args = parser.parse_args()
    if args.vectors:
        build_vectors()
        return
    data = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() and not args.force else {}
    data.update({"source": "Wikivoyage (ru, en)", "license": "CC BY-SA 4.0"})
    data.setdefault("articles", {})
    data.setdefault("chunks", [])
    for d in DESTINATIONS:
        if d.id in data["articles"]:
            continue
        art = article("ru", TITLES_RU.get(d.id, d.name))
        if not art or len(art["paragraphs"]) < 5:
            en = article("en", TITLES_EN[d.id]) if d.id in TITLES_EN else None
            art = en if en and len(en["paragraphs"]) > len(art["paragraphs"] if art else []) else art
        if not art:
            print("нет статьи:", d.id)
            continue
        parts = chunks(d.id, art)
        data["articles"][d.id] = {k: art[k] for k in ("title", "revid", "lang", "url")}
        data["chunks"] = [c for c in data["chunks"] if c["dest"] != d.id] + parts
        print(f"{d.name}: {art['lang']} «{art['title']}» → {len(parts)} кусков", flush=True)
        OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        time.sleep(1)
    print(f"Итого: {len(data['articles'])} статей, {len(data['chunks'])} кусков, {OUT.stat().st_size // 1024} КБ")
    build_vectors()


def build_vectors() -> None:
    """Векторы multilingual-e5-small для всех фрагментов: считаются один раз, в работе кодируется только вопрос."""
    import numpy as np

    from domains.trips import embedder, guides

    data = json.loads(OUT.read_text(encoding="utf-8"))
    texts = [guides.passage_text(c) for c in data["chunks"]]
    vectors = embedder.encode(texts, "passage")
    if vectors is None:
        raise SystemExit("Модель эмбеддингов недоступна: нужны onnxruntime, tokenizers и domains/trips/models/e5_small")
    np.save(guides.VECTORS, vectors.astype(np.float16))
    data["vectors_digest"] = guides.digest(texts)
    OUT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Векторы: {vectors.shape[0]} × {vectors.shape[1]}, {guides.VECTORS.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main()
