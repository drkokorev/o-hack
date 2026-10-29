"""Local, bounded dietary preferences; never assert an ingredient is safe."""
from __future__ import annotations

import re

from .textparse import norm

FOODS = {
    "diet_nuts": r"орех(?:и|ов|ам|ами|ах)?",
    "diet_peanuts": r"арахис(?:а|у|ом|е)?",
    "diet_cashew": r"кешью",
    "diet_sesame": r"кунжут(?:а|у|ом|е)?",
    "diet_milk": r"молок(?:о|а|у|ом|е)?",
    "diet_lactose": r"лактоз(?:а|у|ы|ой|е)?",
    "diet_gluten": r"глютен(?:а|у|ом|е)?",
    "diet_seafood": r"морепродукт(?:ы|ов|ам|ами)?",
    "diet_fish": r"рыб(?:а|ы|у|ой|е)?",
    "diet_eggs": r"яйц(?:а|о|ам|ами|ах)?",
    "diet_soy": r"(?:со(?:я|и|ю|ей)|соев\w*)",
    "diet_wheat": r"пшениц(?:а|ы|у|ей|е)?",
    "diet_meat": r"мяс(?:о|а|у|ом|е)?",
    "diet_pork": r"свинин(?:а|ы|у|ой|е)?",
    "diet_strawberry": r"клубник(?:а|и|у|ой|е)?",
}
LABELS = {
    "diet_cashew": "исключить кешью", "diet_sesame": "исключить кунжут",
    "diet_soy": "исключить сою", "diet_wheat": "исключить пшеницу",
    "diet_meat": "исключить мясо", "diet_pork": "исключить свинину",
    "diet_strawberry": "исключить клубнику", "diet_vegan": "веганское питание",
    "diet_vegetarian": "вегетарианское питание", "diet_halal": "халяльное питание",
    "diet_kosher": "кошерное питание",
}
_WORD = "(?:" + "|".join(FOODS.values()) + ")"
# Only read lists after an explicit exclusion/allergy cue; a sentence such as
# "каша на молоке" or "поехать на рыбалку" must not become a prohibition.
_LIST = re.compile(rf"(?:аллерги\w*\s+на|непереносимост\w*(?:\s+на)?|не\s+ем|нельзя|без|"
                   rf"исключ(?:ить|и|ите)|избег\w*)\s+(?P<items>{_WORD}\b(?:\s*\]?\s*(?:,|и|или)\s*{_WORD}\b)*)")
_SINGLE = {key: re.compile(rf"\b{pattern}\b") for key, pattern in FOODS.items()}
_RESTORE = re.compile(rf"(?P<food>{_WORD})\b\s+(?:(?:теперь|больше|снова)\s+)?(?:можно|разрешен\w*|подходит)\b")


def classify_food(text: str) -> tuple[set[str], set[str], bool]:
    value = norm(text)
    added: set[str] = set()
    removed: set[str] = set()
    unknown = False
    for match in _LIST.finditer(value):
        # "не исключать" is not a dietary requirement.
        if re.search(r"\bне\s+$", value[max(0, match.start() - 8):match.start()]):
            continue
        items = match.group("items")
        added.update(key for key, pattern in _SINGLE.items() if pattern.search(items))
        tail = value[match.end():match.end() + 70]
        following = re.match(r"\s*\]?\s*(?:,|и|или)\s*([а-яa-z-]{3,})", tail)
        if following and following.group(1) not in {"еду", "едем", "лечу", "летим", "хочу", "ищу", "нужен", "нужно", "будет"}:
            unknown = unknown or not any(pattern.fullmatch(following.group(1)) for pattern in _SINGLE.values())
    for match in _RESTORE.finditer(value):
        removed.update(key for key, pattern in _SINGLE.items() if pattern.fullmatch(match.group("food")))
    for key, pattern in (("diet_vegan", r"\bвеган\w*\b"), ("diet_vegetarian", r"\bвегетариан\w*\b"),
                         ("diet_halal", r"\bхалял\w*\b"), ("diet_kosher", r"\bкошерн\w*\b")):
        match = re.search(pattern, value)
        if not match:
            continue
        before = value[max(0, match.start() - 28):match.start()]
        after = value[match.end():match.end() + 28]
        if re.search(r"(?:не\s+нуж\w*|не\s+хочу|больше\s+не|убер\w*|\bне)\s*$", before) or re.match(r"\s+не\s+нуж\w*", after):
            removed.add(key)
        else:
            added.add(key)
    return added - removed, removed, unknown
