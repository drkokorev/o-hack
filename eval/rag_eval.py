"""Замер поиска по путеводителям: какой раздел находит каждый способ на размеченных вопросах.

    .venv/bin/python -m eval.rag_eval

Вопрос считается найденным, если раздел лучшего фрагмента (top-1) или хотя бы одного из трёх (top-3) — один из
ожидаемых. Тема вопроса поиску не передаётся: так видно, насколько хорошо ранжирует сам способ, без подсказки
по разделу. Формулировки разговорные, с перефразами и по-английски. Отчёт: eval/rag_report.md.
"""

from __future__ import annotations

from pathlib import Path

from domains.trips import guides

# (направление, вопрос, допустимые теги разделов)
CASES = [
    ("budva", "что посмотреть в старом городе", {"see"}),
    ("budva", "где перекусить недорого", {"eat"}),
    ("budva", "как добраться из аэропорта", {"arrive", "transport"}),
    ("budva", "куда съездить на день из города", {"nearby"}),
    ("sochi", "в каком районе лучше жить у моря", {"areas", "sleep"}),
    ("sochi", "как ездить по городу без машины", {"transport"}),
    ("sochi", "где покататься на лыжах", {"do", "see", "areas", "nearby"}),
    ("sochi", "водопады и ущелья рядом", {"see", "nearby", "do"}),
    ("istanbul", "что попробовать из местной еды", {"eat"}),
    ("istanbul", "не опасно ли гулять вечером", {"safety"}),
    ("istanbul", "как пользоваться общественным транспортом", {"transport"}),
    ("istanbul", "главные мечети и дворцы", {"see"}),
    ("tokyo", "what to see in Tokyo", {"see"}),
    ("tokyo", "is the metro convenient", {"transport"}),
    ("tokyo", "где поесть суши", {"eat"}),
    ("tokyo", "как попасть в город из аэропорта", {"arrive", "transport"}),
    ("rome", "какие музеи посетить", {"see"}),
    ("rome", "где остановиться недорого", {"sleep", "areas"}),
    ("paris", "что посмотреть кроме Эйфелевой башни", {"see"}),
    ("paris", "безопасно ли в метро ночью", {"safety", "transport"}),
    ("dubai", "где купить сувениры и золото", {"buy"}),
    ("dubai", "чем заняться с детьми", {"do", "see"}),
    ("antalya", "лучшие пляжи", {"do", "see", "areas"}),
    ("antalya", "как доехать до Кемера", {"transport", "arrive", "nearby"}),
    ("bali", "где жить серферу", {"areas", "sleep", "do"}),
    ("bali", "храмы и рисовые террасы", {"see", "nearby", "do"}),
    ("kazan", "что посмотреть в кремле", {"see"}),
    ("kazan", "попробовать татарскую кухню", {"eat"}),
    ("spb", "белые ночи и разводные мосты", {"see", "about", "do"}),
    ("spb", "как передвигаться по городу", {"transport"}),
    ("tbilisi", "где поесть хинкали", {"eat"}),
    ("tbilisi", "серные бани", {"see", "do"}),
    # без общих слов с ответом и по-английски — здесь видно, понимает ли поиск смысл
    ("budva", "куда пойти вечером потанцевать", {"drink"}),
    ("budva", "what can I buy as a gift", {"buy"}),
    ("sochi", "где тихо и много зелени", {"see", "nearby", "do", "areas"}),
    ("sochi", "how do I get around the city", {"transport"}),
    ("istanbul", "что привезти домой", {"buy"}),
    ("istanbul", "is it dangerous for tourists", {"safety"}),
    ("istanbul", "where to eat", {"eat"}),
    ("kazan", "what to see", {"see"}),
    ("rome", "сколько стоит перекусить", {"eat"}),
    ("rome", "how to avoid pickpockets", {"safety"}),
    ("paris", "чем удивить ребёнка", {"see", "do"}),
    ("tokyo", "где переночевать подешевле", {"sleep"}),
]
METHODS = ("bm25", "e5", "bm25+navec", "bm25+e5")


def run(method: str) -> tuple[int, int, list[str]]:
    top1 = top3 = 0
    misses = []
    for dest, query, tags in CASES:
        found = guides.search(query, dest=dest, k=3, min_score=0.0, method=method)
        if found and found[0].tag in tags:
            top1 += 1
        if any(s.tag in tags for s in found):
            top3 += 1
        else:
            misses.append(f"{dest}: «{query}» → {found[0].section if found else 'ничего'}")
    return top1, top3, misses


def main() -> None:
    n = len(CASES)
    lines = ["# Поиск по путеводителям: сравнение способов", "",
             f"{n} разговорных вопросов по 13 направлениям (12 из них — без общих слов с ответом или по-английски), тема вопроса поиску не передаётся.", "",
             "| Способ | top-1 | top-3 |", "| :--- | ---: | ---: |"]
    details = []
    for method in METHODS:
        top1, top3, misses = run(method)
        lines.append(f"| {method} | {top1}/{n} ({100 * top1 // n}%) | {top3}/{n} ({100 * top3 // n}%) |")
        print(f"{method:11} top-1 {top1}/{n}  top-3 {top3}/{n}")
        details += [f"\n**{method}** — промахи top-3:"] + [f"- {m}" for m in misses] if misses else []
    Path(__file__).with_name("rag_report.md").write_text("\n".join(lines + details) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
