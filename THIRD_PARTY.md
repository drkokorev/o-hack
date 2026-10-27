# Сторонние библиотеки, данные и сервисы

| Библиотека | Версия | Лицензия | Зачем |
| :--- | :--- | :--- | :--- |
| pydantic | 2.13.5 | MIT | Схемы данных и валидация ответов LLM |
| openai | 3.24.0 | Apache-2.0 | Клиент OpenAI-совместимого API |
| httpx | 0.28.1 | BSD-3-Clause | HTTP-клиент для авторизации GigaChat |
| python-dotenv | 1.2.4 | BSD-3-Clause | Настройки из `.env` |
| fastapi | 0.142.4 | MIT | Веб-приложение и API |
| uvicorn | 0.54.0 | BSD-3-Clause | Сервер |
| Pillow | 13.0.0 | MIT-CMU | Ужатие фото при сборке (`tools/build_images.py`, только для разработки) |
| DuckDB | 1.4.1 | MIT | Чтение Overture Maps из S3 при сборке (`tools/build_hotels.py`, только для разработки) |
| pytest | 9.1.1 | MIT | Тесты (только для разработки) |

| Данные и сервисы | Где используется | Условия |
| :--- | :--- | :--- |
| Open-Meteo Historical Weather и Marine API | `domains/trips/data/climate.json` (собрано `tools/build_climate.py`) | CC BY 4.0, указываем источник в интерфейсе |
| Фотографии Wikimedia Commons | `apps/static/img/` (собрано `tools/build_images.py`), авторы и лицензии — `apps/static/img/credits.json` и подписи на снимках | CC BY, CC BY-SA, CC0, public domain — по каждому файлу |
| Overture Maps Places, релиз 2026-10-21.0 | `domains/trips/data/hotels.json` (собрано `tools/build_hotels.py`): отели, апартаменты, гостевые дома, пляжи | CDLA Permissive 2.0 / Apache 2.0 — по источникам Overture; указываем источник в интерфейсе |
| OurAirports | Координаты аэропортов в `domains/trips/data/hotels.json` | Public domain |
| Natural Earth 110m land | `apps/static/land.geojson`, [источник](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_land.geojson) | Public domain |
| GeoNames через geonamescache 3.0.1 | `domains/trips/data/world_cities.sqlite3`, 161 662 географических записи, извлечённые из `cities1000.json`; код сборки `tools/build_gazetteer.py`. Географические данные © [GeoNames](https://www.geonames.org/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); данные отобраны и преобразованы. SHA-256 исходного wheel: `959d9d850d822f3c16eb7272d476415e42074aa33f1ea85bc2b7cb43b6751c84`. | Данные CC BY 4.0, лицензия библиотеки MIT: `licenses/geonamescache.txt` |
| umpirsky/country-list | `domains/trips/data/countries_ru.json` и русские названия стран в индексе городов; [источник](https://github.com/umpirsky/country-list) | MIT: `licenses/umpirsky-country-list.txt` |
| Шрифты Golos Text, Unbounded (Google Fonts) | `apps/static/fonts/`; локальные копии для работы без обращения к CDN | SIL Open Font License 1.1: `licenses/golos-OFL.txt`, `licenses/unbounded-OFL.txt` |
| LLM через OpenAI-совместимое API (необязательно) | `core/llm.py`, по ключу из `.env` | По условиям провайдера |

Отели — настоящие объекты Overture Maps; их цены, рейтинги, питание и условия, а также рейсы, поезда, трансферы — синтетические, перевозчики вымышленные. Данные Островка не используются, сайты не скрапятся.
