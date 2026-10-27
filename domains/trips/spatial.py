"""Точный поиск ближайшей географической точки без внешних сервисов и зависимостей."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

from .geo import distance_km


def _vector(lat: float, lon: float) -> tuple[float, float, float]:
    latitude, longitude = math.radians(lat), math.radians(lon)
    cos_latitude = math.cos(latitude)
    return cos_latitude * math.cos(longitude), cos_latitude * math.sin(longitude), math.sin(latitude)


@dataclass(slots=True)
class _Node:
    vector: tuple[float, float, float]
    lat: float
    lon: float
    axis: int
    left: _Node | None = None
    right: _Node | None = None


def _build(items: list[tuple[tuple[float, float, float], float, float]], depth: int = 0) -> _Node | None:
    if not items:
        return None
    axis = depth % 3
    items.sort(key=lambda item: item[0][axis])
    mid = len(items) // 2
    vector, lat, lon = items[mid]
    return _Node(vector, lat, lon, axis, _build(items[:mid], depth + 1), _build(items[mid + 1:], depth + 1))


class GeoPointIndex:
    """KD-дерево на единичной сфере: расстояние по хорде сохраняет порядок расстояний по поверхности."""

    def __init__(self, points: Sequence[Sequence[float]]):
        self._root = _build([(_vector(p[0], p[1]), p[0], p[1]) for p in points])

    def nearest_km(self, lat: float, lon: float) -> float | None:
        if self._root is None:
            return None
        target = _vector(lat, lon)
        best_sq, nearest = math.inf, None

        def search(node: _Node | None) -> None:
            nonlocal best_sq, nearest
            if node is None:
                return
            distance_sq = sum((target[i] - node.vector[i]) ** 2 for i in range(3))
            if distance_sq < best_sq:
                best_sq, nearest = distance_sq, node
            delta = target[node.axis] - node.vector[node.axis]
            first, second = (node.left, node.right) if delta < 0 else (node.right, node.left)
            search(first)
            if delta * delta <= best_sq:
                search(second)

        search(self._root)
        assert nearest is not None
        return round(distance_km(lat, lon, nearest.lat, nearest.lon), 1)
