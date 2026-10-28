# Сторонние библиотеки, данные и сервисы

| Библиотека | Версия | Лицензия | Зачем |
| :--- | :--- | :--- | :--- |
| pydantic | 2.13.5 | MIT | Схемы данных и валидация ответов LLM |
| openai | 3.24.0 | Apache-2.0 | Клиент OpenAI-совместимого API |
| httpx | 0.28.1 | BSD-3-Clause | HTTP-клиент для авторизации GigaChat |
| python-dotenv | 1.2.4 | BSD-3-Clause | Настройки из `.env` |
| fastapi | 0.142.4 | MIT | Веб-приложение и API |
| uvicorn | 0.54.0 | BSD-3-Clause | Сервер |
| maxminddb | 3.2.0 | Apache-2.0 | Чтение локального снимка DB-IP без передачи IP стороннему сервису |
| onnx-asr | 0.12.0 | MIT | Локальное распознавание речи GigaAM |
| ONNX Runtime | 1.31.1 | MIT | Выполнение локальной модели голоса на CPU |
| MapLibre GL JS | 6.16.0 | BSD-3-Clause | Глобус и слои карты, локальная копия; лицензия `apps/static/vendor/maplibre/LICENSE.txt` |
| Three.js | 0.186.1 | MIT | Локальный рендер стилизованных 3D-моделей; два модуля уменьшены esbuild 0.25.12 без изменения публичного API; лицензия `apps/static/vendor/three/LICENSE.txt` |
| Pillow | 13.0.0 | MIT-CMU | Ужатие фото при сборке (`tools/build_images.py`, только для разработки) |
| DuckDB | 1.4.1 | MIT | Чтение Overture Maps из S3 при сборке (`tools/build_hotels.py`, только для разработки) |
| pytest | 9.1.1 | MIT | Тесты (только для разработки) |

| Данные и сервисы | Где используется | Условия |
| :--- | :--- | :--- |
| Open-Meteo Historical Weather и Marine API | `domains/trips/data/climate.json` (собрано `tools/build_climate.py`) | CC BY 4.0, указываем источник в интерфейсе |
| Фотографии Wikimedia Commons | `apps/static/img/` (собрано `tools/build_images.py`), авторы и лицензии — `apps/static/img/credits.json` и подписи на снимках | CC BY, CC BY-SA, CC0, public domain — по каждому файлу |
| Overture Maps Places, релиз 2026-10-21.0 | `domains/trips/data/hotels.json` (`tools/build_hotels.py`; шесть городов — `tools/expand_cities_20261027.py`): записи объектов размещения и пляжей | [Источники и лицензии Overture](https://docs.overturemaps.org/attribution/#places): CDLA Permissive 2.0, Apache 2.0 для Foursquare и CC0 для AllThePlaces. Foursquare: Copyright 2024 Foursquare Labs, Inc., [NOTICE](https://opensource.foursquare.com/os-places/NOTICE.txt). Не все старые записи сохраняют исходный ID или точного первичного поставщика. |
| OurAirports | Координаты аэропортов в `domains/trips/data/hotels.json`; снимок 48 101 аэродрома в `domains/trips/data/ourairports.json` (`tools/fetch_airports.py`) | [Public domain](https://ourairports.com/data/), источник не гарантирует точность. Это не расписания и не подтверждение наличия билетов. |
| Natural Earth 110m land | `apps/static/land.geojson`, [источник](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_land.geojson) | Public domain |
| Natural Earth 110m countries | `apps/static/countries.geojson`, контуры и точки подписи стран, [исходные данные](https://github.com/nvkelso/natural-earth-vector/blob/master/geojson/ne_110m_admin_0_countries.geojson); преобразованы и сохранены только нужные поля | Public domain |
| DB-IP Country Lite | `domains/trips/data/dbip-country-lite-2026-10.mmdb.gz`, снимок за октябрь 2026; [DB-IP](https://db-ip.com/) | CC BY 4.0; указание источника в интерфейсе |
| ЦБ РФ | Снимок курсов за 28.10.2026 в `apps/static/exchange-rates.json`; [сервис XML](https://www.cbr.ru/development/sxml/) | Только приблизительный пересчёт демонстрационных сумм, не актуальный курс оплаты |
| Источники событий | Ссылки организаторов и дата ручной проверки в `apps/static/events.json` | Программа и билеты не обновляются автоматически |
| UNESCO World Heritage List, набор whc001 | 108 преобразованных записей и координаты их единственных компонентов в `apps/static/heritage.json`, снимок 28.10.2026; [источник](https://data.unesco.org/explore/dataset/whc001/) | UNESCO, [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Координата компонента не обязательно указывает вход. Созданы выборка и русские подписи; восстановление из JSON-экспорта — `python tools/build_heritage_20261028.py --input путь_к_экспорту.json`. |
| NASA Earth Observatory, Blue Marble Next Generation | `apps/static/assets/earth-blue-marble-200410.jpg`, [исходный снимок за октябрь 2004](https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/base-map/) | [NASA разрешает свободное использование и изменение](https://science.nasa.gov/blogs/earth-matters/2011/10/06/crafting-the-blue-marble/); изменены цвет, масштаб и освещение. Изображение историческое, не спутниковый поток в реальном времени. |
| Эйфелева башня | `apps/static/assets/eiffel-tower.glb`: [( FREE ) La tour Eiffel](https://sketchfab.com/3d-models/free-la-tour-eiffel-8553f94d06e24cb4b0fde1080f281674), автор SDC PERFORMANCE™️ | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); модель упрощена с 147 604 до 35 424 треугольников, изменены масштаб, материал и освещение. Оригинальный GLB получен из [демонстрации Smart UI](https://www.htmlelements.com/demos/3d-chart/custom-models/). |
| Бурдж-Халифа | `apps/static/assets/burj-khalifa.glb`: [Burj Khalifa](https://sketchfab.com/3d-models/burj-khalifa-59e6dd74e5f647158de568b5a7f9cab7), автор ManySince910 | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); для карты изменены масштаб, цвет материала и освещение. Оригинальный GLB получен из [демонстрации Smart UI](https://www.htmlelements.com/demos/3d-chart/custom-models/). |
| Гоночный автомобиль | `apps/static/assets/formula-car.glb`, [apex-formula-2026](https://github.com/ahacker-1/apex-formula-2026/blob/main/ASSET_PROVENANCE.md) | Apache-2.0; лицензия `licenses/apex-apache-2.0.txt` и уведомление `licenses/apex-NOTICE.txt`. Геометрия оригинала сохранена, масштаб и освещение изменены для карты. Концептуальная модель без принадлежности к команде. |
| Wikidata | Координаты отдельных достопримечательностей и автодрома в карточках и JSON; ссылки указаны по объектам | [CC0 1.0](https://www.wikidata.org/wiki/Wikidata:Licensing); точность точек зависит от источника. |
| GeoNames через geonamescache 3.0.1 | `domains/trips/data/world_cities.sqlite3`, 161 662 географических записи, извлечённые из `cities1000.json`; код сборки `tools/build_gazetteer.py`. Географические данные © [GeoNames](https://www.geonames.org/), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/); данные отобраны и преобразованы. SHA-256 исходного wheel: `959d9d850d822f3c16eb7272d476415e42074aa33f1ea85bc2b7cb43b6751c84`. | Данные CC BY 4.0, лицензия библиотеки MIT: `licenses/geonamescache.txt` |
| umpirsky/country-list | `domains/trips/data/countries_ru.json` и русские названия стран в индексе городов; [источник](https://github.com/umpirsky/country-list) | MIT: `licenses/umpirsky-country-list.txt` |
| Шрифты Golos Text, Unbounded (Google Fonts) | `apps/static/fonts/`; локальные копии для работы без обращения к CDN | SIL Open Font License 1.1: `licenses/golos-OFL.txt`, `licenses/unbounded-OFL.txt` |
| LLM через OpenAI-совместимое API (необязательно) | `core/llm.py`, по ключу из `.env` | По условиям провайдера |

Объекты размещения и 8 точек категории campground (`domains/trips/data/campgrounds.json`, `tools/fetch_campgrounds.py`) взяты из Overture Maps; актуальность каждого объекта и сайта не проверена. Их цены, рейтинги, питание и условия, а также рейсы, поезда, трансферы — синтетические, перевозчики вымышленные. Бесплатный API Open-Meteo отдельно ограничен некоммерческим использованием; CC BY 4.0 для данных не отменяет [условий сервиса](https://open-meteo.com/en/terms). Данные Островка не используются, сайты не скрапятся.
