"""Быстрый обзор выданных данных: что за таблицы, какие колонки, пропуски, примеры значений.

    .venv/bin/python -m tools.inspect_data data/            # все файлы в папке
    .venv/bin/python -m tools.inspect_data data/hotels.csv --out data/profile.md

Отчёт в Markdown печатается в консоль и (с --out) сохраняется в файл. В конце — какие колонки
загрузчик каталога распознал автоматически и сколько отелей из файла получилось бы.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from domains.hotels.loader import detect_mapping, read_rows, to_hotels

FORMATS = {".csv", ".json", ".jsonl", ".parquet", ".xlsx", ".xls"}


def _cell(value: object, limit: int = 60) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str) if isinstance(value, (list, dict)) else str(value)
    text = text.replace("|", "\\|").replace("\n", " ")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def profile(path: Path) -> str:
    rows = read_rows(path)
    df = pd.DataFrame(rows)
    out = [f"## {path.name}", "", f"Строк: {len(df)}, колонок: {len(df.columns)}", ""]
    out += ["| Колонка | Тип | Пустых | Уникальных | Примеры |", "| :--- | :--- | ---: | ---: | :--- |"]
    for col in df.columns:
        series = df[col]
        hashable = series.map(lambda v: json.dumps(v, ensure_ascii=False, default=str)
                              if isinstance(v, (list, dict)) else v)
        nulls = int(series.isna().sum() + (series.astype(str).str.strip() == "").sum())
        examples = ", ".join(_cell(v, 40) for v in hashable.dropna().unique()[:3])
        out.append(f"| {col} | {series.dtype} | {nulls / max(len(df), 1):.0%} | {hashable.nunique()} | {examples} |")

    numeric = df.select_dtypes("number")
    if not numeric.empty:
        out += ["", "Числовые колонки:", "", numeric.describe().T.round(2).to_markdown()]

    mapping = detect_mapping(df.columns)
    out += ["", f"Загрузчик распознал: `{json.dumps(mapping, ensure_ascii=False)}`"]
    try:
        hotels = to_hotels(rows)
        cities = pd.Series([h.city for h in hotels]).value_counts()
        out += [f"Отелей из файла: {len(hotels)}; городов: {len(cities)}; топ: "
                + ", ".join(f"{c} ({n})" for c, n in cities.head(8).items())]
    except ValueError as err:
        out += [f"Как каталог отелей не читается: {err}"]
    out += ["", "Первые строки:", "", df.head(3).map(_cell).to_markdown(index=False), ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    files = sorted(p for p in args.path.rglob("*") if p.suffix.lower() in FORMATS) if args.path.is_dir() else [args.path]
    report = []
    for f in files:
        try:
            report.append(profile(f))
        except Exception as err:  # отчёт по остальным файлам важнее одного битого
            report.append(f"## {f.name}\n\nНе прочитан: {err}\n")
    text = "# Обзор данных\n\n" + "\n".join(report)
    print(text)
    if args.out:
        args.out.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
