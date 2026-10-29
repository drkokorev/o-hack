"""Versioned fixture data, validated before a demo provider can be used."""
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class DemoConfig(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True)
    version: Literal[1]
    source: Literal['synthetic']
    airlines: tuple[str, ...] = Field(min_length=1)
    hub_moscow: tuple[Annotated[float, Field(ge=-90, le=90)], Annotated[float, Field(ge=-180, le=180)]]
    all_inclusive_places: frozenset[str]
    prefix: tuple[str, ...] = Field(min_length=1)
    kinds: tuple[tuple[str, int], ...] = Field(min_length=1)
    praise: dict[str, str]
    complaints: tuple[str, ...] = Field(min_length=2)
    real_kinds: dict[str, str]
    kind_stars: dict[str, tuple[Annotated[int, Field(ge=1, le=5)], ...]]


def load_demo_config(path: Path | None = None) -> DemoConfig:
    path = path or Path(__file__).parent.parent / 'data' / 'demo_inventory.json'
    return DemoConfig.model_validate_json(path.read_text(encoding='utf-8'))
