"""Параметры поиска отеля, состояние диалога и то, что извлекается из одной реплики."""

from datetime import date

from pydantic import BaseModel, Field


class HotelParams(BaseModel):
    """Параметры поиска. Только их видит и заполняет LLM."""

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


PARAM_FIELDS = tuple(HotelParams.model_fields)


class HotelState(HotelParams):
    """Состояние диалога: параметры плюс служебные поля, которые ведёт код домена."""

    shown_prices: list[int] = Field(default_factory=list, description="Цены за ночь в последней выдаче")

    def params(self) -> HotelParams:
        return HotelParams.model_validate(self.model_dump(include=set(PARAM_FIELDS)))


class HotelUpdate(HotelParams):
    new_search: bool | None = Field(None, description="true, только если пользователь начинает поиск с нуля")
    cheaper: bool | None = Field(None, description="true, если просит варианты дешевле показанных")
    clear: list[str] | None = Field(
        None, description="Параметры, которые пользователь просит не учитывать: budget_max, stars_min, "
        "amenities, near_center, near_sea, district, trip_purpose, check_in"
    )
