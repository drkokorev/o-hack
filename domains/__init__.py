from datetime import date


def build_domain(name: str, today: date | None = None):
    if name == "hotels":
        from .hotels.domain import HotelsDomain

        return HotelsDomain()
    if name == "clinic":
        from .clinic.domain import ClinicDomain

        return ClinicDomain(today=today)
    raise ValueError(f"Неизвестный домен: {name}")
