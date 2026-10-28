"""Synthetic offline privacy and travel-text evaluation; makes no model API calls."""
from __future__ import annotations

import argparse
import json
import time
import unicodedata
from pathlib import Path
from statistics import median

from core.guard import contains_unresolved_sensitive_data, mask_sensitive_data
from domains.trips.domain import TripsDomain


ROOT = Path(__file__).parent

# Values are invented. Coverage means only that the listed literal value is
# absent after filtering; it is not a claim about all personal information.
CASES = [
    ("name_1", "Для Ирины Смирновой подберите отдых в Сочи", "Ирины Смирновой"),
    ("name_2", "Я Сергей, еду в Казань в июне", "Сергей"),
    ("name_3", "Меня зовут елена орлова, хочу на море", "елена орлова"),
    ("name_4", "Поедем вместе с Николаем Петровым в Турцию", "Николаем Петровым"),
    ("name_5", "Сын Андрей Иванов хочет в Сочи", "Андрей Иванов"),
    ("name_6", "Guest Jane Miller wants to visit Paris", "Jane Miller"),
    ("phone_1", "В Сочи на неделю, контакт +7 (999) 123-45-67", "+7 (999) 123-45-67"),
    ("phone_2", "Телефон 8 912 345-67-89, хочу в Казань", "8 912 345-67-89"),
    ("phone_3", "Телефон 9123456789, еду в Сочи", "9123456789"),
    ("phone_4", "Звоните +49 151 23456789, хочу в Сочи", "+49 151 23456789"),
    ("email_1", "Высылайте на marina@example.org, хочу в Сочи", "marina@example.org"),
    ("email_2", "Напишите на test\u200b@example.net, едем в Казань", "test@example.net"),
    ("passport_1", "Паспорт 4510 123456, еду в Сочи", "4510 123456"),
    ("passport_2", "Паспорт серия 4510 номер 123456, еду в Сочи", "4510"),
    ("card_1", "Карта 4111 1111 1111 1111, нужен отель в Сочи", "4111 1111 1111 1111"),
    ("snils_1", "СНИЛС 123-456-789 01, ищу поездку в Казань", "123-456-789 01"),
    ("snils_2", "123-456-789 01, ищу поездку в Казань", "123-456-789 01"),
    ("inn_1", "ИНН 123456789012, хочу в Сочи", "123456789012"),
    ("birth_1", "Дата рождения 12.03.1985, хочу в Сочи", "12.03.1985"),
    ("birth_2", "Я родилась 12.03.1985, хочу в Сочи", "12.03.1985"),
    ("address_1", "Мой адрес: Москва, Лесная 8, хочу в Сочи", "Лесная 8"),
    ("address_2", "Я живу по адресу улица Тестовая 12, хочу в Казань", "Тестовая 12"),
    ("address_3", "улица Тестовая, дом 12, квартира 3, едем в Сочи", "Тестовая"),
    ("password_1", "Пароль: synthetic-pass, хочу в Сочи", "synthetic-pass"),
    ("token_1", "API key: synthetic-token, хочу в Казань", "synthetic-token"),
    ("ip_1", "Мой адрес сети 192.0.2.13, еду в Сочи", "192.0.2.13"),
]

# This more difficult set deliberately contains cases that a detector might
# miss; results must be reported, not hidden or considered a passing guarantee.
CHALLENGES = [
    ("spoken_phone", "мой телефон девятьсот двенадцать триста сорок пять шестьдесят семь", "девятьсот двенадцать"),
    ("written_email", "моя почта marina собака example точка ru, хочу в Сочи", "marina собака example"),
    ("lowercase_name", "поездка для анны ивановой в Сочи", "анны ивановой"),
    ("health", "у меня диабет, хочу поездку в Сочи", "диабет"),
    ("customer_id", "мой номер клиента 12345678, хочу в Казань", "12345678"),
    ("unlabeled_address", "живу возле станции Лесная в доме 12, хочу в Сочи", "Лесная"),
]


def normalized(text: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFKC", text).casefold()
                   if unicodedata.category(ch) != "Cf")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    places = TripsDomain.preserve_place
    timings, checks = [], []
    for group, cases in (("common", CASES), ("challenge", CHALLENGES)):
        for ident, text, secret in cases:
            start = time.perf_counter()
            cleaned, detected = mask_sensitive_data(text, places)
            timings.append(time.perf_counter() - start)
            checks.append({"group": group, "id": ident, "detected": detected,
                           "secret_removed": normalized(secret) not in normalized(cleaned),
                           "text": text, "filtered": cleaned})

    normal = []
    for path in sorted(ROOT.glob("dialogue_*_20261027.json")):
        for case in json.loads(path.read_text(encoding="utf-8")):
            for turn in case["turns"]:
                text = turn["text"]
                cleaned, detected = mask_sensitive_data(text, places)
                normal.append({"set": path.name, "case": case["id"], "text": text,
                               "filtered": cleaned, "changed": detected or cleaned != text,
                               "local_only": contains_unresolved_sensitive_data(cleaned)})
    normal_changed = [item for item in normal if item["changed"]]
    normal_local_only = [item for item in normal if item["local_only"]]
    common = [item for item in checks if item["group"] == "common"]
    challenge = [item for item in checks if item["group"] == "challenge"]
    report = {"common_removed": sum(item["secret_removed"] for item in common),
              "common_total": len(common),
              "challenge_removed": sum(item["secret_removed"] for item in challenge),
              "challenge_total": len(challenge),
              "normal_total": len(normal), "normal_changed": len(normal_changed),
              "normal_local_only": len(normal_local_only),
              "median_filter_seconds": round(median(timings), 4),
              "checks": checks, "normal_changes": normal_changed, "normal_local_only_cases": normal_local_only}
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"common: {report['common_removed']}/{report['common_total']}; "
          f"challenge: {report['challenge_removed']}/{report['challenge_total']}; "
          f"normal changed: {report['normal_changed']}/{report['normal_total']}; "
          f"normal local-only: {report['normal_local_only']}; "
          f"filter median: {report['median_filter_seconds']} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
