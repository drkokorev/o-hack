"""Small source-labelled campground snapshot; it does not verify pitches or facilities."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

DATA = Path(__file__).with_name("data") / "campgrounds.json"


@lru_cache(maxsize=1)
def _load() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8")) if DATA.exists() else {"campgrounds": {}}


def campground_hint(dest_id: str) -> str | None:
    data = _load()
    records = data.get("campgrounds", {}).get(dest_id, [])
    if not records:
        return None
    record = records[0]
    return (f"В карте Overture Maps (снимок {data['release']}) есть объект «{record['name']}» в этом районе. "
            "Подходит ли он для своей палатки, разрешён ли огонь и есть ли места, нужно уточнить отдельно.")
