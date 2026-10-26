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
# Галерея направления: лучшие снимки Commons (Quality images / Featured pictures) по видовым запросам
GALLERY = {
    "sochi": ["Sochi sea", "Krasnaya Polyana", "Sochi Olympic Park", "Sochi Adler", "Rosa Khutor"],
    "kaliningrad": ["Kaliningrad", "Curonian Spit", "Zelenogradsk", "Svetlogorsk"],
    "kazan": ["Kazan Kremlin", "Kazan", "Kul Sharif"], "spb": ["Saint Petersburg", "Peterhof", "Neva"],
    "moscow": ["Moscow Kremlin", "Moscow", "Moscow City"], "kislovodsk": ["Kislovodsk", "Pyatigorsk", "Elbrus"],
    "altai": ["Altai Republic", "Katun", "Lake Teletskoye", "Altai mountains"],
    "baikal": ["Lake Baikal", "Olkhon", "Listvyanka"], "murmansk": ["Teriberka", "Murmansk", "Khibiny"],
    "dagestan": ["Dagestan", "Sulak canyon", "Derbent", "Gunib"], "vladivostok": ["Vladivostok", "Russky Island"],
    "kamchatka": ["Kamchatka volcano", "Avachinsky", "Kamchatka"], "sheregesh": ["Sheregesh", "Gornaya Shoria"],
    "karelia": ["Karelia", "Kizhi", "Ruskeala", "Valaam"], "nnovgorod": ["Nizhny Novgorod", "Nizhny Novgorod Kremlin"],
    "antalya": ["Antalya", "Kaleiçi", "Konyaaltı", "Kemer", "Side Turkey"],
    "istanbul": ["Istanbul", "Bosphorus", "Hagia Sophia", "Blue Mosque"],
    "dubai": ["Dubai", "Dubai Marina", "Burj Khalifa", "Palm Jumeirah"],
    "hurghada": ["Hurghada", "Red Sea Egypt", "Giftun"], "sharm": ["Sharm el-Sheikh", "Ras Mohammed", "Sinai Red Sea"],
    "phuket": ["Phuket", "Phang Nga", "Patong", "Phi Phi"], "nhatrang": ["Nha Trang", "Khanh Hoa"],
    "sanya": ["Sanya", "Hainan beach", "Yalong Bay"], "maldives": ["Maldives", "Maldives beach", "Maldives island"],
    "srilanka": ["Sri Lanka", "Sigiriya", "Galle", "Ella Sri Lanka", "Mirissa"],
    "tbilisi": ["Tbilisi", "Narikala", "Mtskheta"], "batumi": ["Batumi", "Adjara"],
    "yerevan": ["Yerevan", "Ararat", "Garni", "Khor Virap"], "samarkand": ["Samarkand", "Registan", "Shah-i-Zinda"],
    "baku": ["Baku", "Baku Old City", "Flame Towers"], "minsk": ["Minsk", "Mir Castle", "Nesvizh"],
    "almaty": ["Almaty", "Medeu", "Big Almaty Lake", "Charyn"], "bali": ["Bali", "Ubud", "Bali temple", "Bali beach"],
    "goa": ["Goa India", "Goa beach", "Panaji"],
}
# Отобранные вручную снимки галереи (из кандидатов `--candidates`): виды, а не цветы, стадионы и интерьеры
GALLERY_FILES: dict[str, list[str]] = {
    "sochi": [
        "File:Black Sea near Sochi.jpg",
        "File:Krasnaya Polyana P5020282 2200.jpg",
        "File:Krasnaya Polyana Rosa Khutor P5020173 2175.jpg",
        "File:Alpine resort Gazprom in Krasnaya Polyana.jpg",
        "File:Фейерверк в морском порту Сочи 9 мая 2015 года.jpg",
    ],
    "kaliningrad": [
        "File:Дюна Эфа с высоты.jpg",
        "File:Kaliningrad fishing village.jpg",
    ],
    "kazan": [
        "File:Kazan Kremlin exterior view 08-2016 img3.jpg",
        "File:Kazan Kul Sharif Mosque 2024-07-13 1322.jpg",
        "File:Kazan Kremlin exterior view 08-2016 img1.jpg",
        "File:Kazan Kremlin. Spasskaya Tower P8111872 2200.jpg",
    ],
    "spb": [
        "File:Peter & Paul fortress in SPB 03.jpg",
        "File:Spb 06-2012 English Embankment 01.jpg",
        "File:Петергоф Дворец и Большой Каскад.jpg",
        "File:Церковь Большого Дворца. Петергоф.jpg",
    ],
    "moscow": [
        "File:Vista general del Kremlin, Moscú, Rusia, 2016-10-03, DD 18-19 HDR.jpg",
        "File:Moscow State University crop.jpg",
        "File:Moscow 05-2017 img13 Krymsky Bridge.jpg",
        "File:Museo Estatal de Historia, Moscú, Rusia, 2016-10-03, DD 49.jpg",
    ],
    "kislovodsk": [
        "File:Cascading staircase Kislovodsk.jpg",
        "File:Вид на Эльбрус по пути в Джилы-Су.jpg",
        "File:Beshtau Mountain IMG 4945.jpg",
        "File:Lake Azau (Lake Elbrus) 3264 m.jpg",
    ],
    "altai": [
        "File:Сказка,Мечта,Красавица.jpg",
        "File:Teletskoye lake. Dawn in the village of Artybash at the source of the Biya.jpg",
        "File:Panorama from the Chike-Taman pass in the north direction.jpg",
        "File:Kosh Agach panorama.jpg",
    ],
    "baikal": [
        "File:Baikal, Cape Burhan, Olkhon Island, Lake Baikal, Russia.jpg",
        "File:Olkhon Island, Capes, cliffs at sunset, Lake Baikal, Russia.jpg",
        "File:Lake Baikal in winter.jpg",
        "File:Shamanic ritual pillars at Cape Burhan, Olkhon Island, Lake Baikal.jpg",
    ],
    "murmansk": [
        "File:Teriberka.jpg",
        "File:Khibiny mountain range. The Lake Bolshoy Vudyavr.jpg",
        "File:Kandalaksha Bay.jpg",
        "File:An Array Of Khibiny.jpg",
    ],
    "dagestan": [
        "File:Вид на каньон и реку Сулак у поселка Дубки.jpg",
        "File:Dagestan-015.jpg",
        "File:Dagestan-041.jpg",
    ],
    "vladivostok": [
        "File:Vladivostok Zolotoy Rog Bay P8050527 2200.jpg",
        "File:Russkiy Island.jpg",
        "File:Vladivostok Ocean Avenue 30 2024-08 1725118076.jpg",
        "File:Vladivostok Batareinaya street Amur Bay embankment 2024-08 016.jpg",
    ],
    "kamchatka": [
        "File:Корякский, Авачинский, Козельский.jpg",
        "File:Малый Семячик.jpg",
        "File:Kamchatka Brown Bear near Dvuhyurtochnoe on 2015-07-23.jpg",
        "File:Лиса-огневка на фоне Вилючинского вулкана.jpg",
    ],
    "sheregesh": [
        "File:Поселок Шерегеш - panoramio.jpg",
        "File:Шерегеш и горы.jpg",
        "File:Шерегеш восход и туман.jpg",
    ],
    "karelia": [
        "File:KizhiIsland 008 1125.jpg",
        "File:Valaam 3 2018.jpg",
        "File:Kizhi Island P7110064 2200.jpg",
    ],
    "nnovgorod": [
        "File:NN Chkalov Stairs 08-2016 img3.jpg",
        "File:NN Spit from Kanavinsky Bridge 08-2016.jpg",
        "File:Nizhny Novgorod. Kremlin P5180733 2800.jpg",
        "File:Nizhny Novgorod Kremlin (view from Volga).jpg",
    ],
    "antalya": [
        "File:Antalya kaleiçi 2.jpg",
        "File:Hadrian's Gate, Antalya 01.jpg",
        "File:Konyaaltı Beach, Antalya, Turkey, March 2022 - Harrington Park Resort.jpg",
    ],
    "istanbul": [
        "File:Hagia Sophia Mars 2013.jpg",
        "File:Exterior of Sultan Ahmed I Mosque in Istanbul, Turkey 002.jpg",
        "File:Blue Mosque Courtyard Dusk Wikimedia Commons.jpg",
        "File:Istanbul asv2020-02 img55 View of Beşiktaş.jpg",
    ],
    "dubai": [
        "File:Madinat Jumeirah-Dubai3303.JPG",
        "File:Dubai creek-2011 (7).JPG",
        "File:Desierto de dubai-2011 (4).JPG",
        "File:(UAE) The Dubai Fountain at Dusk 02.jpg",
    ],
    "hurghada": [
        "File:Hurghada Beach Albatros 01.jpg",
        "File:Coral reefs in the Red Sea.jpg",
        "File:Hurghada Marina 002.jpg",
    ],
    "sharm": [
        "File:Tortuga carey (Eretmochelys imbricata), parque nacional Ras Muhammad, Egipto, 2022-03-28, DD 56.jpg",
        "File:Pez ángel real (Pygoplites diacanthus), parque nacional Ras Muhammad, Egipto, 2022-03-26, DD 155.jpg",
        "File:Almeja gigante (Tridacna maxima), Temple, Sharm el-Sheij, Egipto, 2022-03-26, DD 33.jpg",
    ],
    "phuket": [
        "File:Isla Tapu, Phuket, Tailandia, 2013-08-20, DD 36.JPG",
        "File:Isla Phi Phi Lay, Tailandia, 2013-08-19, DD 04.JPG",
        "File:Playa Maya, Ko Phi Phi, Tailandia, 2013-08-19, DD 13.JPG",
        "File:Phuket - Kata Beach 001.jpg",
    ],
    "nhatrang": [
        "File:Hòn Nội, Nha Trang Bay, Vietnam.jpg",
        "File:Arriving in Nha Trang - Vietnam.jpg",
        "File:Nha Trang fishing village.jpg",
        "File:Nha Trang Beach, Vietnam.jpg",
    ],
    "sanya": [
        "File:三亚太阳湾公路旁海滩 20260115.jpg",
        "File:Lighthouse near Daxiao Dongtian 20260120.jpg",
    ],
    "maldives": [
        "File:Diamonds Thudufushi Beach and Water Villas, May 2017 -08.jpg",
        "File:Diamonds Thudufushi Beach and Water Villas, May 2017 -09.jpg",
        "File:Whale Shark AdF.jpg",
        "File:Male-total.jpg",
    ],
    "srilanka": [
        "File:Sri Lankan elephant (Elephas maximus maximus) female and young 6.jpg",
        "File:SL Demodara near Ella asv2020-01 img02.jpg",
        "File:SL Anuradhapura asv2020-01 img31 Abhayagiriya Stupa.jpg",
    ],
    "tbilisi": [
        "File:20110421 Tbilisi Georgia Panoramic.jpg",
        "File:Narikala, Tiflis, Georgia, 2016-09-29, DD 91.jpg",
        "File:Georgia Jvari monastery IMG 9345 2070.jpg",
        "File:Mtskheta and Svetitskhoveli Cathedral 3x2.jpg",
    ],
    "batumi": [
        "File:Batumi sunset.jpg",
        "File:Batumi beach (84).jpg",
        "File:Batumi Boulevard Colonnades.jpg",
    ],
    "yerevan": [
        "File:Mount Ararat and the Yerevan skyline.jpg",
        "File:Monasterio Khor Virap, Armenia, 2016-10-01, DD 25.jpg",
        "File:Templo de Garni, Armenia, 2016-10-02, DD 03.jpg",
        "File:Khor Virap Monastery 2, Ararat Plain, Armenia.jpg",
    ],
    "samarkand": [
        "File:Registan 01.jpg",
        "File:Самарканд. Площадь-Регистан.jpg",
        "File:Shah-i-Zinda 04.jpg",
        "File:Tilya-Kori Madrasa 01.jpg",
    ],
    "baku": [
        "File:Vista de Baku, Azerbaiyán, 2016-09-26, DD 138.jpg",
        "File:Fuente en Baku, Azerbaiyán, 2016-09-26, DD 227-229 HDR.jpg",
        "File:Baku, Azerbaiyán, 2016-09-28, DD 29.jpg",
        "File:Baku, Azerbaiyán, 2016-09-26, DD 211.jpg",
    ],
    "minsk": [
        "File:Комплекс Мирского замка.JPG",
        "File:Belarus Nesvizh Castle 7259 2050.jpg",
        "File:Niasviž Castle South Side 2023-07-03 6246.jpg",
        "File:Minsk HolySpiritChurch 001 3673.jpg",
    ],
    "almaty": [
        "File:БАО ранней осенью.jpg",
        "File:Charyn Canyon, Kazakhstan 04.jpg",
        "File:Медео, стадион с плотины (2).jpg",
        "File:Вид на вершину МЮД и на ледник Колесника из цирка Ледника Туристов, верховья Левого Талгара.jpg",
    ],
    "bali": [
        "File:Besakih Bali Indonesia Pura-Besakih-02.jpg",
        "File:Fields in Ubud, Bali, Indonesia, 20220822 1501 0161.jpg",
        "File:Fields in Ubud, Bali, Indonesia, 20220822 1344 0125.jpg",
        "File:Sunset, Kuta, Bali, Indonesia, 20220825 1755 0879.jpg",
    ],
    "goa": [
        "File:Anjuna Beach, Goa, India, Legendary Curlies beach shack.jpg",
        "File:Mandrem Beach and Mandrem River, Mandrem, Goa, India (edit).jpg",
        "File:Panaji - Church of Our Lady of the Immaculate Conception - 1.jpg",
        "File:Streets of Fontainhas, Panaji (04).jpg",
    ],
}
_BAD = re.compile(r"map|karte|flag|coat|logo|plan|scheme|insect|beetle|butterfl|moth|bird|flower|lilium|orchid|"
                  r"spider|portrait|interior|inside|museum|icon|fresco|altar|ceiling|detail|sign|plate|stamp|"
                  r"tram|train|bus|car\b|locomotive|aircraft|airplane|ship|boat|truck|grave|tomb|crossing|"
                  r"сх[её]ма|карта|герб|флаг|интерьер|жук|бабочк|цвет", re.I)


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


def search_best(query: str, limit: int = 20) -> list[str]:
    """Сначала избранные и качественные снимки Commons — они отобраны сообществом и красивы."""
    found: list[str] = []
    for cat in ("Featured_pictures_on_Wikimedia_Commons", "Quality_images"):
        url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&list=search&srnamespace=6"
               f"&srlimit={limit}&srsearch={quote(f'{query} incategory:{cat} filetype:bitmap')}")
        found += [h["title"] for h in get_json(url)["query"]["search"]
                  if re.search(r"\.jpe?g$", h["title"], re.I) and not _BAD.search(h["title"])]
    return found


def landscape(filename: str) -> dict | None:
    """Только горизонтальные кадры нормального размера — для обложек и карточек."""
    url = ("https://commons.wikimedia.org/w/api.php?action=query&format=json&prop=imageinfo"
           f"&iiprop=size|mime&titles={quote(filename)}")
    page = next(iter(get_json(url)["query"]["pages"].values()))
    info = (page.get("imageinfo") or [{}])[0]
    w, h = info.get("width", 0), info.get("height", 1)
    if "jpeg" not in (info.get("mime") or "") or w < 1400 or not 1.25 <= w / h <= 2.3:
        return None
    return file_info(filename)


def candidates(dest_id: str, limit: int = 12) -> list[str]:
    """Кандидаты в галерею: по очереди из каждого видового запроса, чтобы были и море, и горы, и город."""
    used = {c["file"] for c in json.loads((OUT / "credits.json").read_text()).values()}
    pools = [[t for t in search_best(q) if t not in used] for q in GALLERY.get(dest_id, [])]
    out: list[str] = []
    for rank in range(20):
        for pool in pools:
            if rank < len(pool) and pool[rank] not in out and len(out) < limit and landscape(pool[rank]):
                out.append(pool[rank])
    return out


def gallery(dest_id: str, credits: dict, force: bool) -> None:
    """Скачиваем отобранные снимки GALLERY_FILES (отбор — вручную по `--candidates`)."""
    for n, filename in enumerate(GALLERY_FILES.get(dest_id, []), 1):
        key = f"gallery/{dest_id}-{n}.jpg"
        if key in credits and credits[key]["file"] == filename and (OUT / key).exists() and not force:
            continue
        info = file_info(filename)
        if not info:
            print("нет файла:", filename)
            continue
        download(info, OUT / key)
        credits[key] = {k: info[k] for k in ("file", "page", "author", "license")}
        print("ок", key, filename[5:70], info["license"])
        time.sleep(1)


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
    parser.add_argument("--candidates", metavar="DEST", help="показать кандидатов в галерею направления")
    args = parser.parse_args()
    if args.candidates:
        for i, t in enumerate(candidates(args.candidates)):
            print(i, t)
        return
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
        if have and not args.force:  # отобранные вручную иллюстрации не трогаем
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
    (OUT / "gallery").mkdir(parents=True, exist_ok=True)
    for dest_id in DESTINATIONS:
        try:
            gallery(dest_id, credits, args.force)
        except Exception as err:  # сеть или лимит API — остальное не теряем
            print("ошибка галереи", dest_id, err)
        credits_path.write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    credits_path.write_text(json.dumps(credits, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Файлов:", len(credits))


if __name__ == "__main__":
    main()
