def build_domain(name: str):
    if name == "hotels":
        from .hotels.domain import HotelsDomain

        return HotelsDomain()
    raise ValueError(f"Неизвестный домен: {name}")
