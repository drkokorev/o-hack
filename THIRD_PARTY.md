# Сторонние библиотеки, данные и сервисы

| Библиотека | Версия | Лицензия | Зачем |
| :--- | :--- | :--- | :--- |
| pydantic | 2.13.5 | MIT | Схемы данных и валидация ответов LLM |
| openai | 3.24.0 | Apache-2.0 | Клиент OpenAI-совместимого API |
| python-dotenv | 1.2.4 | BSD-3-Clause | Настройки из `.env` |
| fastapi | 0.142.4 | MIT | Веб-приложение и API |
| uvicorn | 0.54.0 | BSD-3-Clause | Сервер |
| Pillow | 13.0.0 | MIT-CMU | Ужатие фото при сборке (`tools/build_images.py`, только для разработки) |
| DuckDB | 1.4.1 | MIT | Чтение Overture Maps из S3 при сборке (`tools/build_hotels.py`, только для разработки) |
| pytest, httpx | 9.1.1, 0.28.1 | MIT, BSD-3-Clause | Тесты (только для разработки) |

| Данные и сервисы | Где используется | Условия |
| :--- | :--- | :--- |
| Open-Meteo Historical Weather и Marine API | `domains/trips/data/climate.json` (собрано `tools/build_climate.py`) | CC BY 4.0, указываем источник в интерфейсе |
| Фотографии Wikimedia Commons | `apps/static/img/` (собрано `tools/build_images.py`), авторы и лицензии — `apps/static/img/credits.json` и подписи на снимках | CC BY, CC BY-SA, CC0, public domain — по каждому файлу |
| Overture Maps Places, релиз 2026-10-21.0 | `domains/trips/data/hotels.json` (собрано `tools/build_hotels.py`): отели, апартаменты, гостевые дома, пляжи | CDLA Permissive 2.0 / Apache 2.0 — по источникам Overture; указываем источник в интерфейсе |
| OurAirports | Координаты аэропортов в `domains/trips/data/hotels.json` | Public domain |
| Natural Earth 110m land | `apps/static/landdots.json` (собрано `tools/build_landdots.py`) | Public domain |
| Шрифты Golos Text, Unbounded (Google Fonts) | `apps/static/index.html` | SIL Open Font License 1.1 |
| LLM через OpenAI-совместимое API (необязательно) | `core/llm.py`, по ключу из `.env` | По условиям провайдера |

Отели — настоящие объекты Overture Maps; их цены, рейтинги, питание и условия, а также рейсы, поезда, трансферы — синтетические, перевозчики вымышленные. Данные Островка не используются, сайты не скрапятся.
