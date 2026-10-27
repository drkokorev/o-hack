from random import Random

import pytest

from domains.trips.geo import distance_km
from domains.trips.spatial import GeoPointIndex


def test_nearest_geographic_point_matches_brute_force_across_world():
    rng = Random(731)
    points = [[rng.uniform(-89, 89), rng.uniform(-180, 180)] for _ in range(400)]
    points.extend([[0, 179.99], [0, -179.99], [89.9, 0]])
    index = GeoPointIndex(points)
    queries = [(rng.uniform(-89, 89), rng.uniform(-180, 180)) for _ in range(60)]
    queries.extend([(0, 180), (89.99, 180), (-40, 170)])
    for lat, lon in queries:
        expected = round(min(distance_km(lat, lon, p[0], p[1]) for p in points), 1)
        assert index.nearest_km(lat, lon) == expected


def test_empty_index_and_antipodal_distance_are_well_defined():
    assert GeoPointIndex([]).nearest_km(0, 0) is None
    assert distance_km(0, 0, 0, 180) == pytest.approx(20015.09, abs=0.1)
