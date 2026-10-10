"""Состояние поиска отеля и то, что LLM извлекает из одной реплики."""

from datetime import date

from pydantic import BaseModel, Field


class HotelState(BaseModel):
    city: str | None = Field(None, description="Город в именительном падеже")
    check_in: date | None = Field(None, description="Дата заезда YYYY-MM-DD")
    check_out: date | None = Field(None, description="Дата выезда YYYY-MM-DD")
    guests: int | None = Field(None, description="Число гостей")
    budget_max: int | None = Field(None, description="Максимальная цена за ночь, руб.")
    stars_min: int | None = Field(None, description="Минимальная звёздность 1–5")
    amenities: list[str] | None = Field(None, description="Коды обязательных удобств")
    near_center: bool | None = Field(None, description="Хочет ближе к центру")
    near_sea: bool | None = Field(None, description="Хочет ближе к морю")
    district: str | None = Field(None, description="Конкретный район или достопримечательность")
    trip_purpose: str | None = Field(None, description="family | business | romantic | budget")


class HotelUpdate(HotelState):
    new_search: bool | None = Field(None, description="true, только если пользователь начинает поиск с нуля")
