"""Explicit access needs, never inferred diagnoses or supplier capabilities.

Only a small, bounded vocabulary is retained in the trip state. Matching takes
place locally; source text and health details are not retained in these fields.
"""
from __future__ import annotations

import re

from .textparse import norm
from .dietary import LABELS as DIET_LABELS, classify_food


LABELS = {
    "wheelchair": "поездка с инвалидной коляской",
    "mobility_aid": "средство для передвижения",
    "stroller_unspecified": "коляска: тип не уточнён",
    "baby_stroller": "детская коляска",
    "step_free": "маршрут без ступенек",
    "lift": "нужен лифт",
    "ramp": "нужен пандус или подъёмник",
    "accessible_room": "адаптированный номер или ванная",
    "airport_assistance": "помощь в аэропорту или при посадке",
    "visual_assistance": "сопровождение или доступная навигация",
    "text_communication": "текстовые уведомления или связь",
    "guide_dog": "собака-проводник",
    "quiet_room": "тихое размещение",
    "medical_equipment": "перевозка медицинского оборудования",
    "dietary": "ограничение питания",
    "diet_nuts": "исключить орехи",
    "diet_peanuts": "исключить арахис",
    "diet_milk": "исключить молоко",
    "diet_lactose": "исключить лактозу",
    "diet_gluten": "исключить глютен",
    "diet_seafood": "исключить морепродукты",
    "diet_fish": "исключить рыбу",
    "diet_eggs": "исключить яйца",
    "unspecified": "условия доступности нужно уточнить",
}
LABELS.update(DIET_LABELS)

_PATTERNS = {
    "wheelchair": r"инвалидн\w*\s+(?:кресл\w*|коляск\w*)|кресл\w*[- ]коляск\w*|\bэлектроколяск\w*|\b(?:wheelchair|wheel[ -]?chair)\b|"
                  r"\b(?:в|на)\s+(?:электрическ\w*\s+)?коляск\w*\b|"
                  r"(?:пользу\w*|передвига\w*)\s+(?:на\s+)?(?:инвалидн\w*\s+)?(?:коляск\w*|кресл\w*)",
    "mobility_aid": r"\b(?:с|на)\s+(?:костыл\w*|трость\w*|тростью|ходунк\w*)\b",
    "stroller_unspecified": r"\b(?:с|со|в|на)\s+коляск\w*\b",
    "baby_stroller": r"детск\w*\s+коляск\w*|коляск\w*\s+для\s+(?:малыш\w*|младен\w*)",
    "step_free": r"без\s+(?:лестниц\w*|ступен\w*|порог\w*)|безбарьерн\w*|"
                 r"(?:не\s+(?:могу|может|можем)\s+(?:ходить|подниматься|подняться)\s+по\s+лестниц\w*)",
    "lift": r"(?:не\s+)?(?:нуж\w*|важ\w*|обязател\w*|с)\s+лифт\w*|лифт\w*\s+(?:больше\s+)?не\s+нуж\w*",
    "ramp": r"(?:не\s+)?(?:нуж\w*|важ\w*|обязател\w*|с)\s+(?:пандус|подъемник)\w*|"
            r"(?:пандус|подъемник)\w*\s+(?:больше\s+)?не\s+нуж\w*",
    "accessible_room": r"(?:адаптированн\w*|доступн\w*)\s+(?:номер|ванн\w*|санузел|душ)\b|"
                       r"(?:номер|ванн\w*|санузел|душ)\s+для\s+(?:коляск\w*|маломобильн\w*|инвалид\w*)",
    "airport_assistance": r"(?:помощ\w*|сопровожд\w*)\s+(?:в\s+аэропорт\w*|при\s+посадк\w*|"
                          r"на\s+посадк\w*|при\s+пересадк\w*)|(?:нуж\w*|заказать)\s+(?:ассист\w*|сопровожд\w*)\s+в\s+аэропорт\w*",
    "visual_assistance": r"(?:сопровожд\w*|помощ\w*|навигац\w*)\s+(?:для\s+)?(?:незряч\w*|слеп\w*|слабовидящ\w*)|"
                         r"(?:нуж\w*|важ\w*)\s+(?:тактильн\w*|голосов\w*)\s+(?:указател\w*|навигац\w*)",
    "text_communication": r"(?:текстов\w*|письменн\w*)\s+(?:уведомлен\w*|связ\w*|сообщен\w*|общени\w*)|"
                          r"(?:не\s+звон\w*|пишит\w*\s+вместо\s+звон\w*|(?:пишит\w*|отвечайт\w*)\s+письменно)",
    "guide_dog": r"собак\w*[- ]проводник\w*|собак\w*[- ]помощник\w*|\bguide\s+dog\b|\bservice\s+dog\b",
    "quiet_room": r"(?:тих\w*|без\s+шум\w*)\s+(?:номер|комнат\w*|размещени\w*)|"
                  r"(?:номер|комнат\w*)\s+(?:потише|без\s+шум\w*)",
    "medical_equipment": r"(?:медицинск\w*|дыхательн\w*)\s+(?:оборудован\w*|аппарат\w*|прибор\w*)|"
                         r"(?:перевоз\w*|вез\w*|брать)\s+(?:кислородн\w*\s+)?концентратор\w*",
    "dietary": r"\[условие питания:\s*исключить\b|\b(?:аллерги\w*|непереносимост\w*)\s+на\s+[а-яa-z]+|"
               r"(?:питани\w*|ед\w*)\s+без\s+(?:орех\w*|арахис\w*|глютен\w*|лактоз\w*)",
    "diet_nuts": r"(?:исключить|исключени\w*|без)\s+орех(?:и|ов|ам|ами|ах)?\b",
    "diet_peanuts": r"(?:исключить|исключени\w*|без)\s+арахис(?:а|у|ом|е)?\b",
    "diet_milk": r"(?:исключить|исключени\w*|без)\s+молок(?:о|а|у|ом|е)?\b",
    "diet_lactose": r"(?:исключить|исключени\w*|без)\s+лактоз(?:а|у|ы|ой|е)?\b",
    "diet_gluten": r"(?:исключить|исключени\w*|без)\s+глютен(?:а|у|ом|е)?\b",
    "diet_seafood": r"(?:исключить|исключени\w*|без)\s+морепродукт(?:ы|ов|ам|ами)?\b",
    "diet_fish": r"(?:исключить|исключени\w*|без)\s+рыб(?:а|ы|у|ой|е)?\b",
    "diet_eggs": r"(?:исключить|исключени\w*|без)\s+яйц(?:а|о|ам|ами|ах)?\b",
    "unspecified": r"\b(?:инвалид\w*|ограниченн\w*\s+(?:возможност\w*|подвижност\w*)|маломобильн\w*|"
                   r"незряч\w*|слабовидящ\w*|слабослышащ\w*|глух\w*)\b|"
                   r"\b(?:я|он|она|пассажир)\s+слеп\w*\b",
}
_COMPILED = {key: re.compile(value) for key, value in _PATTERNS.items()}
_IDENTITY_ONLY = frozenset({"unspecified"})
_NEG_BEFORE = re.compile(r"(?:не\s+(?:нуж\w*|требу\w*|надо|хочу)|убер\w*|исключ\w*|отмен\w*|"
                         r"больше\s+не\s+нуж\w*)\s+(?:\w+\s+){0,2}$")
_NEG_AFTER = re.compile(r"^\s+(?:больше\s+)?не\s+(?:нуж\w*|требу\w*|надо|поед\w*|полет\w*)\b")
_CHILD_STROLLER = re.compile(r"(?:детск\w*|малыш\w*|ребен\w*|младен\w*|груднич\w*)")


def classify(text: str) -> tuple[set[str], set[str]]:
    """Return requested and explicitly removed needs; ambiguous baby strollers are excluded."""
    value = norm(text)
    add: set[str] = set()
    remove: set[str] = set()
    for key, pattern in _COMPILED.items():
        for match in pattern.finditer(value):
            if key == "wheelchair" and not re.search(r"инвалид|электроколяск|кресл\w*[- ]коляск|wheel", match.group()):
                nearby = value[max(0, match.start() - 45):min(len(value), match.end() + 25)]
                if _CHILD_STROLLER.search(nearby):
                    continue
            before = value[max(0, match.start() - 50):match.start()]
            after = value[match.end():match.end() + 45]
            if (_NEG_BEFORE.search(before) or _NEG_AFTER.search(after) or
                    (key == "unspecified" and re.search(r"\b(?:не|нет)\s+$", before)) or
                    re.search(r"\bне\s+нуж\w*", match.group())):
                remove.add(key)
            else:
                add.add(key)
    dietary_added, dietary_removed, dietary_unknown = classify_food(text)
    add.update(dietary_added)
    remove.update(dietary_removed)
    if dietary_unknown:
        add.add("dietary")
    # An explicit wheelchair or specific help makes the generic identity term
    # unnecessary; a diagnosis/identity alone never implies a particular aid.
    if add - _IDENTITY_ONLY:
        add.discard("unspecified")
    if add & {"wheelchair", "baby_stroller"}:
        add.discard("stroller_unspecified")
    if any(key.startswith("diet_") for key in add) and not dietary_unknown:
        add.discard("dietary")
    return add - remove, remove


def needs_local_handling(text: str) -> bool:
    """Use the local parser for recognized accessibility/health-related turns."""
    added, removed = classify(text)
    return bool(added or removed or re.search(r"\b(?:инвалид\w*|маломобильн\w*|незряч\w*|"
                                               r"слабовидящ\w*|слабослышащ\w*)\b", norm(text)))


def notice(needs: list[str], scope: str | None, transport: str | None = None) -> str:
    """State the boundary first, then give practical checks without assumptions."""
    have = set(needs)
    if have == {"unspecified"}:
        return ("Если для поездки важны условия доступности, напишите, какие именно: например, "
                "вход без ступенек, помощь при посадке или текстовая связь. Диагноз указывать не нужно.")
    if have == {"stroller_unspecified"}:
        return ("Уточните, пожалуйста, какая коляска имеется в виду: детская или средство передвижения пассажира? "
                "Условия перевозки пока не проверены, запрос поставщику не отправлен.")
    labels = [LABELS[key] for key in LABELS if key in have and key != "unspecified"]
    intro = "Учёл пожелания: " + ", ".join(labels) + ". "
    boundary = ("Доступность конкретных вариантов не проверена: они не отобраны по этим условиям. "
                "Запрос на помощь поставщику не отправлен.")
    guidance = []
    if have & {"wheelchair", "mobility_aid", "airport_assistance", "visual_assistance", "medical_equipment"} and scope not in {"hotel_only", "transfer_only", "split_hotel"}:
        if scope == "train_only" or (scope != "flight_only" and transport == "train"):
            guidance.append("Для поезда уточните у перевозчика помощь при посадке, доступное место и перевозку необходимых средств.")
        else:
            guidance.append("Для перелёта уточните у перевозчика необходимую помощь в аэропорту и при посадке, а также условия перевозки нужных средств." +
                            (" Для электроколяски уточните условия аккумулятора." if "wheelchair" in have else ""))
    if have & {"wheelchair", "step_free", "lift", "ramp", "accessible_room"} and scope not in {"flight_only", "train_only", "transfer_only"}:
        guidance.append("У жилья проверьте вход, лифт, проходы и удобства конкретного номера.")
    if "wheelchair" in have and scope not in {"flight_only", "train_only", "hotel_only", "split_hotel"}:
        guidance.append("Для трансфера отдельно подтвердите подходящую машину и посадку.")
    if "guide_dog" in have:
        guidance.append("У перевозчика и жилья отдельно уточните условия для собаки-проводника.")
    if "dietary" in have or any(key.startswith("diet_") for key in have):
        guidance.append("Состав блюд и исключения уточняйте у поставщика питания; при аллергии отдельно проверьте риск перекрёстного контакта с аллергенами.")
    if "dietary" in have:
        guidance.append("Название продукта не распознано; уточните его отдельно у поставщика.")
    if "stroller_unspecified" in have:
        guidance.append("Уточните, какая коляска имеется в виду: детская или средство передвижения пассажира.")
    if "baby_stroller" in have:
        guidance.append("Уточните у перевозчика условия перевозки детской коляски и её размещение в трансфере.")
    return " ".join([intro + boundary, *guidance])
