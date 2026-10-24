def build_domain(name: str = "trips"):
    if name == "trips":
        from .trips.domain import TripsDomain

        return TripsDomain()
    raise ValueError(f"Неизвестный домен: {name}")
