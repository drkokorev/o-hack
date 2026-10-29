"""Explicit traveller and animal requirements; no inferred eligibility or medical advice."""
from __future__ import annotations

import re

from .textparse import norm

LABELS = {
    "pregnancy": "условия поездки при беременности",
    "older_traveler": "пожилой путешественник",
    "retiree": "указан статус пенсионера",
    "senior_fare": "уточнить льготный тариф",
    "child_seat": "детское автокресло",
    "baby_cot": "детская кроватка",
    "unaccompanied_minor": "ребёнок без взрослого сопровождающего",
}
PET_LABELS = {"dog": "собака", "cat": "кошка", "bird": "птица", "rabbit": "кролик"}
_PET = {
    "dog": r"собак\w*|собач\w*|пес(?:а|ик|иком)?|пс(?:а|ом|у)?|щен\w*",
    "cat": r"кошк\w*|кот(?:а|у|ом|ик|енок|енка)?",
    "bird": r"попуга\w*|птиц\w*",
    "rabbit": r"кролик\w*|кролич\w*",
}
_PET_WORD = r"(?:" + "|".join(_PET.values()) + r")"
_NUM = {"один": 1, "одна": 1, "одну": 1, "одним": 1, "два": 2, "две": 2, "двух": 2,
        "двумя": 2, "три": 3, "трех": 3, "тремя": 3, "четыре": 4, "четырех": 4}
_PREG = re.compile(r"\[условия беременности\]|\bбеременн\w*\b")
_OLDER = re.compile(r"\b(?:пожил\w*|пенсионер\w*|пенсионн\w*\s+(?:скидк\w*|льгот\w*|тариф\w*))\b")
_QUESTION = re.compile(r"\b(?:можно\s+ли|есть\s+ли|какие|какой|сколько|каков\w*|положен\w*\s+ли)\b")


def local_only(text: str) -> bool:
    value = norm(text)
    return bool(_PREG.search(value) or _OLDER.search(value) or
                re.search(r"\b(?:ребенк\w*|ребенок|дети|детей|детям|малыш\w*|младен\w*|сын\w*|дочк\w*|дочер\w*)\b[^.!?;]{0,30}\b\d{1,3}\b", value) or
                re.search(r"\b(?:ребен\w*|сын\w*|доч\w*|несовершеннолетн\w*)\b[^.!?;]{0,60}\bбез\s+(?:взросл\w*|сопровожд\w*)", value))


def removed_pet_types(text: str, existing: list[str] | None) -> set[str]:
    value = norm(text)
    return {key for key in (existing or []) if key in _PET and
            re.search(rf"\bбез\s+(?:{_PET[key]})\b", value)}


def classify(text: str, state, parsed) -> dict:
    """Extract bounded values only when the person explicitly supplied them."""
    value = norm(text)
    added: set[str] = set()
    removed: set[str] = set()
    topics: set[str] = set()
    pregnancy = _PREG.search(value)
    if pregnancy:
        before = value[max(0, pregnancy.start() - 35):pregnancy.start()]
        if re.search(r"\bне\s*$", before):
            removed.add("pregnancy")
        elif re.search(r"\bпланиру\w*\s*$", before):
            topics.add("pregnancy")
        elif ("?" in text or _QUESTION.search(value)) and not re.search(
                r"\b(?:я|мы|меня|жена|супруга|пассажирк\w*)\b", value):
            topics.add("pregnancy")
        else:
            added.add("pregnancy")
            if "?" in text or _QUESTION.search(value):
                topics.add("pregnancy")
    if _OLDER.search(value):
        discount = bool(re.search(r"скидк\w*|льгот\w*|спецтариф\w*|пенсионн\w*\s+тариф\w*", value))
        discount_removed = bool(re.search(r"(?:не\s+нуж\w*|убер\w*|сним\w*|без)\s+(?:пенсионн\w*\s+)?(?:скидк\w*|льгот\w*|тариф\w*)|"
                                          r"(?:скидк\w*|льгот\w*)\s+(?:больше\s+)?не\s+нуж\w*", value))
        question_only = bool(("?" in text or _QUESTION.search(value)) and
                             not re.search(r"\b(?:я|мы|еду|едем|путешеств\w*|мам\w*|пап\w*|бабушк\w*|дедушк\w*)\b", value))
        if discount_removed:
            removed.add("senior_fare")
        elif discount:
            topics.add("senior_fare")
            if not question_only and ("?" not in text or re.search(r"хочу|нуж\w*|ищу|подбер\w*", value)):
                added.add("senior_fare")
        if not question_only and re.search(r"\b(?:я|мы|еду|едем|путешеств\w*|мам\w*|пап\w*|бабушк\w*|дедушк\w*|для)\b", value):
            if re.search(r"\bпожил\w*\b", value):
                added.add("older_traveler")
            if re.search(r"\bпенсионер\w*\b", value):
                added.add("retiree")
    for key, pattern in (("child_seat", r"детск\w*\s+(?:автокресл\w*|кресл\w*)|автокресл\w*\s+для\s+ребен\w*"),
                         ("baby_cot", r"детск\w*\s+кроватк\w*|кроватк\w*\s+для\s+(?:ребен\w*|малыш\w*)")):
        match = re.search(pattern, value)
        if match:
            before = value[max(0, match.start() - 25):match.start()]
            after = value[match.end():match.end() + 25]
            if re.search(r"(?:не\s+нуж\w*|убер\w*)\s*$", before) or re.match(r"\s+не\s+нуж\w*", after):
                removed.add(key)
            else:
                added.add(key)
    if "baby_cot" in (state.travel_needs or []) and re.search(r"\bкроватк\w*\s+(?:больше\s+)?не\s+нуж\w*", value):
        removed.add("baby_cot")
    if "child_seat" in (state.travel_needs or []) and re.search(r"\bавтокресл\w*\s+(?:больше\s+)?не\s+нуж\w*", value):
        removed.add("child_seat")
    if "senior_fare" in (state.travel_needs or []) and re.search(r"(?:убер\w*|сним\w*|без)\s+(?:эту\s+)?(?:скидк\w*|льгот\w*)|"
            r"(?:скидк\w*|льгот\w*)\s+(?:больше\s+)?не\s+нуж\w*", value):
        removed.add("senior_fare")
    if re.search(r"\b(?:ребен\w*|ребенок|сын\w*|доч\w*|несовершеннолетн\w*)\b[^.!?;]{0,65}"
                 r"(?:без\s+(?:взросл\w*|сопровожд\w*)|(?:едет|летит|поедет|полетит)\s+(?:один|одна))", value):
        added.add("unaccompanied_minor")

    changes = {}
    if added:
        changes["travel_needs"] = sorted(added)
    if removed:
        changes["remove_travel_needs"] = sorted(removed)
    if topics:
        changes["question"] = "|".join(dict.fromkeys([*((parsed.question or "").split("|") if parsed.question else []), *sorted(topics)]))

    # Guide dogs are separate. Animal details from a general policy question
    # must not turn the hypothetical animal into a traveller.
    animal_text = re.sub(r"собак\w*[- ](?:проводник|помощник)\w*", " ", value)
    actual_pet = parsed.pets is True or (state.pets is True and parsed.pets is not False)
    question_only = bool(("?" in text or _QUESTION.search(value)) and parsed.pets is None and
                         not re.search(r"\b(?:мой|моя|мою|наш|наша|едем|лечу|летим)\b", value))
    if actual_pet and not question_only:
        species = sorted(key for key, pattern in _PET.items() if re.search(rf"\b(?:{pattern})\b", animal_text))
        if species and state.pet_types and (re.search(r"^\s*(?:а\s+)?(?:и|еще|также|плюс)\b", animal_text) or
                (len(state.pet_types) > 1 and not re.search(r"\b(?:только|лишь|вместо|замен\w*)\b", animal_text))):
            # Mentioning one of several animals does not remove the others.
            species = sorted(set(species) | set(state.pet_types))
        if species:
            changes["pet_types"] = species
        total = re.search(rf"\bвсего\s+(\d{{1,2}}|{'|'.join(_NUM)})\s+(?:животн\w*|питомц\w*)\b", animal_text)
        count = total or (re.search(rf"\b(\d{{1,2}}|{'|'.join(_NUM)})\s+(?:{_PET_WORD})\b", animal_text)
                          if len(species or state.pet_types or []) <= 1 else None)
        if count:
            number = int(count.group(1)) if count.group(1).isdigit() else _NUM[count.group(1)]
            if 1 <= number <= 10:
                changes["pet_count"] = number
        weight = (re.search(rf"\b(?:{_PET_WORD}|питомец|животное)\s*(?:(?:весит|вес|весом|около|примерно)\s*)?(\d{{1,3}}(?:[.,]\d{{1,2}})?)\s*кг\b", animal_text)
                  or re.search(rf"\bвес\s+(?:{_PET_WORD}|питомца|животного)\s*(?:около\s*)?(\d{{1,3}}(?:[.,]\d{{1,2}})?)\s*кг\b", animal_text))
        if weight and len(species or state.pet_types or []) <= 1 and (changes.get("pet_count") or state.pet_count or 1) == 1:
            number = float(weight.group(1).replace(",", "."))
            if 0 < number <= 200:
                changes["pet_weight_kg"] = number
        if (len(species or state.pet_types or []) <= 1 and (changes.get("pet_count") or state.pet_count or 1) == 1
                and re.search(r"\b(?:в\s+салон(?:е)?|в\s+кабин(?:у|е))\b", animal_text) and (species or state.pets)
                and not re.search(r"(?:багаж|чемодан)\w*[^.!?;]{0,25}\bв\s+(?:салон|кабин)", animal_text)):
            changes["pet_cabin"] = not bool(re.search(r"\bне\s+в\s+(?:салон|кабин)", animal_text))
    return changes


def notice(needs: list[str], scope: str | None) -> str:
    have = set(needs)
    parts = []
    if "pregnancy" in have:
        parts.append("Учёл, что важны условия поездки при беременности. Безопасность поездки и применимые требования не проверены: "
                     "индивидуальные вопросы обсудите с врачом, условия перевозчика и страховки уточните отдельно. Срок и диагноз сообщать здесь не нужно.")
    if "senior_fare" in have:
        parts.append("Льготный тариф пока не подтверждён и в демоцены не включён; право на скидку и её условия проверяет перевозчик.")
    if "child_seat" in have:
        parts.append("Детское автокресло сохранено как пожелание; его наличие и соответствие возрасту нужно подтвердить у трансфера.")
    if "baby_cot" in have:
        parts.append("Детская кроватка сохранена как пожелание; наличие и условия нужно подтвердить у жилья.")
    if "unaccompanied_minor" in have:
        parts.append("Поездка ребёнка без взрослого сопровождающего зависит от правил перевозчика и маршрута; "
                     "условия и услуга сопровождения не проверены. Взрослого в состав не добавляю.")
    if have and have <= {"older_traveler", "retiree"}:
        parts.append("Если важны темп поездки, помощь при посадке или доступность жилья, можно указать пожелания; "
                     "возраст или статус сами по себе не задают ограничений.")
    return " ".join(parts)
