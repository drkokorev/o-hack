"""Restore the checked, open-data map snapshot for this standalone branch.

The generated SQLite index is not committed. A later integration can replace
this adapter and snapshot with the team's rebuilt catalogue without touching
the dialogue or its model state.
"""
from __future__ import annotations

import gzip
from contextlib import closing
import os
import shutil
import sqlite3
import tempfile
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "domains" / "trips" / "data"
ARCHIVE = DATA / "map_catalog-snapshot-20261027.sqlite3.gz"
DATABASE = DATA / "map_catalog.sqlite3"


def ensure_snapshot() -> Path:
    if DATABASE.is_file():
        return DATABASE
    if not ARCHIVE.is_file():
        raise FileNotFoundError("Снимок каталога карты отсутствует")
    fd, temp_name = tempfile.mkstemp(prefix="odin-map-", suffix=".sqlite3", dir=DATA)
    temporary = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as out, gzip.open(ARCHIVE, "rb") as compressed:
            shutil.copyfileobj(compressed, out, length=1024 * 1024)
        with closing(sqlite3.connect(temporary.resolve().as_uri() + "?mode=ro", uri=True)) as db:
            if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                raise ValueError("Снимок каталога повреждён")
        if not DATABASE.exists():
            try:
                os.replace(temporary, DATABASE)
            except OSError:
                # Another worker may have restored the same snapshot first.
                if not DATABASE.is_file():
                    raise
    finally:
        temporary.unlink(missing_ok=True)
    return DATABASE


if __name__ == "__main__":
    print(ensure_snapshot())
