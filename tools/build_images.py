"""Фотографии направлений и иллюстрации отелей из Wikimedia Commons (свободные лицензии) в apps/static/img/.

    .venv/bin/python -m tools.build_images            # всё, что ещё не скачано
    .venv/bin/python -m tools.build_images --force    # перекачать

Для направления берётся главное фото статьи Википедии о характерном месте (или явно заданный файл Commons),
для отелей — небольшой набор иллюстраций по типу (пляжный отель, городской, номер, бассейн). Автор и лицензия
каждого файла сохраняются в apps/static/img/credits.json и показываются в интерфейсе.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

OUT = Path(__file__).resolve().parent.parent / "apps" / "static" / "img"
UA = {"User-Agent": "o-odin-zapros/1.0 (hackathon prototype; github.com/ostrovok-hackathon-2026)"}
WIDTH = 1280

# id направления → статья ru.wikipedia (её главное фото) или "File:…" на Commons
DESTINATIONS = {
    "sochi": "Сочи", "kaliningrad": "Куршская коса", "kazan": "Казанский кремль", "spb": "Дворцовая площадь",
    "moscow": "Красная площадь", "kislovodsk": "Кисловодск", "altai": "Телецкое озеро", "baikal": "Байкал",
    "murmansk": "File:Полярное сияние под Кировском 3.jpg", "dagestan": "Сулакский каньон", "vladivostok": "File:Russky Bridge 2022-08.jpg",
    "kamchatka": "Ключевская Сопка", "sheregesh": "Шерегеш", "karelia": "Кижи", "nnovgorod": "Нижегородский кремль",
    "antalya": "Анталья", "istanbul": "Айя-София", "dubai": "File:Dubai Skyline mit Burj Khalifa (cropped).jpg", "hurghada": "File:Hurghada beach 01.JPG",
    "sharm": "Шарм-эш-Шейх", "phuket": "Пхукет", "nhatrang": "File:Nha Trang Beach 5.jpg", "sanya": "File:Strand in der Yalong Bay Bucht in Sanya auf der Insel Hainan.jpg", "maldives": "File:Diamonds Thudufushi Beach and Water Villas, May 2017 -03.jpg",
    "srilanka": "Сигирия", "tbilisi": "File:Old Town and Narikala, Tbilisi.jpg", "batumi": "Батуми", "yerevan": "Ереван", "samarkand": "File:Registan Samarkand Uzbekistan.JPG",
    "baku": "File:Flame towers from Baku boulevard.JPG", "minsk": "Минск", "almaty": "Медеу", "bali": "Бали", "goa": "File:Vagator Beach, Goa, India, Palms.jpg",
}
# Иллюстрации отелей по типу: поиск по Commons, берём первые подходящие фото
HOTEL_QUERIES = {
    "resort": "beach resort hotel pool sea", "city": "hotel facade city street", "room": "hotel room bed interior",
    "pool": "hotel swimming pool", "mountain": "mountain hotel chalet", "lobby": "hotel lobby interior",
}
PER_QUERY = 3


def fetch(url: str, timeout: int = 60) -> bytes:
    """GET с повторами: Википедия отвечает 429 при частых запросах."""
    from urllib.error import HTTPError

    for attempt in range(6):
        try:
            with urlopen(Request(url, headers=UA), timeout=timeout) as resp:
                return resp.read()
        except HTTPError as err:
            if err.code not in (429, 503) or attempt == 5:
                raise
            wait = int(err.headers.get("Retry-After") or 0) or 5 * (attempt + 1)
            print(f"  {err.code}, жду {wait} с")
            time.sleep(wait)
    raise RuntimeError("недостижимо")


def get_json(url: str) -> dict:
    return json.loads(fetch(url, 30))


def file_info(filename: str) -> dict | None:
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo"
           f"&iiprop=url|extmetadata|mime&iiurlwidth={WIDTH}&titles={quote(filename)}")
    pages = get_json(url)["query"]["pages"]
    page = next(iter(pages.values()))
    if "imageinfo" not in page:
        return None
    info = page["imageinfo"][0]
    meta = info.get("extmetadata", {})
    strip = lambda html: re.sub(r"<[^>]+>", "", html or "").strip()  # noqa: E731
    return {"file": filename, "thumb": info.get("thumburl") or info["url"], "page": info.get("descriptionurl"),
            "mime": info.get("mime"), "author": strip(meta.get("Artist", {}).get("value"))[:80] or "Wikimedia Commons",
            "license": strip(meta.get("LicenseShortName", {}).get("value")) or "см. страницу файла"}


def page_image(title: str) -> str | None:
    data = get_json(f"https://ru.wikipedia.org/api/rest_v1/page/summary/{quote(title)}")
    src = (data.get("originalimage") or data.get("thumbnail") or {}).get("source")
    if not src:
        return None
    src = src.split("?")[0]
    name = src.split("/")[-1]
    if re.match(r"\d+px-", name):  # это уже миниатюра — берём исходное имя из пути
        name = src.split("/")[-2]
    return "File:" + requests_unquote(name)


def requests_unquote(s: str) -> str:
    from urllib.parse import unquote
    return unquote(s)


def search_files(query: str, limit: int) -> list[str]:
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&list=search&srnamespace=6"
           f"&srlimit={limit * 4}&srsearch={quote(query + ' filetype:bitmap')}")
    hits = get_json(url)["query"]["search"]
    return [h["title"] for h in hits if re.search(r"\.jpe?g$", h["title"], re.I)][: limit * 2]


def compress(path: Path, width: int = 1000, quality: int = 70) -> None:
    """Ужимаем до ширины `width` и прогрессивного JPEG — карточкам больше не нужно, страница грузится быстро."""
    try:
        from PIL import Image
    except ImportError:  # Pillow нужен только при сборке картинок
        return
    with Image.open(path) as im:
        im = im.convert("RGB")
        if im.width > width:
            im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        im.save(path, "JPEG", quality=quality, optimize=True, progressive=True)


def download(info: dict, path: Path) -> None:
    path.write_bytes(fetch(info["thumb"]))
    compress(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    (OUT / "dest").mkdir(parents=True, exist_ok=True)
    (OUT / "hotel").mkdir(parents=True, exist_ok=True)
    credits_path = OUT / "credits.json"
    credits = json.loads(credits_path.read_text()) if credits_path.exists() and not args.force else {}

    for dest_id, title in DESTINATIONS.items():
        path = OUT / "dest" / f"{dest_id}.jpg"
        if path.exists() and not args.force and f"dest/{dest_id}.jpg" in credits:
            continue
        filename = title if title.startswith("File:") else page_image(title)
        info = file_info(filename) if filename else None
        if not info or "jpeg" not in (info.get("mime") or ""):
            print("нет фото:", dest_id, filename)
            continue
        download(info, path)
        credits[f"dest/{dest_id}.jpg"] = {k: info[k] for k in ("file", "page", "author", "license")}
        print("ок", dest_id, info["file"], info["license"])
        time.sleep(2)

    for kind, query in HOTEL_QUERIES.items():
        have = [k for k in credits if k.startswith(f"hotel/{kind}-")]
        if len(have) >= PER_QUERY and not args.force:
            continue
        n = 0
        for filename in search_files(query, PER_QUERY):
            info = file_info(filename)
            if not info or "jpeg" not in (info.get("mime") or ""):
                continue
            n += 1
            key = f"hotel/{kind}-{n}.jpg"
            download(info, OUT / key)
            credits[key] = {k: info[k] for k in ("file", "page", "author", "license")}
            print("ок", key, info["file"], info["license"])
            time.sleep(2)
            if n >= PER_QUERY:
                break
    for f in OUT.rglob("*.jpg"):
        compress(f)
    credits_path.write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Файлов:", len(credits))


if __name__ == "__main__":
    main()
