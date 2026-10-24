"""Параметры поездки, состояние диалога и то, что извлекается из одной реплики."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class TripParams(BaseModel):
    """Пожелания путешественника. Только их видит и заполняет LLM."""

    origin: str | None = Field(None, description="Город вылета в именительном падеже")
    destination: str | None = Field(None, description="Куда едет: город, курорт или страна, если назван")
    trip_types: list[str] | None = Field(None, description="Коды типа отдыха: sea, beach, warm, mountains, ski, "
                                         "city, culture, nature, food, spa, exotic")
    month: int | None = Field(None, description="Месяц поездки 1–12, если точных дат нет")
    date_from: date | None = Field(None, description="Дата начала поездки YYYY-MM-DD")
    date_to: date | None = Field(None, description="Дата окончания поездки YYYY-MM-DD")
    nights: int | None = Field(None, description="Число ночей")
    adults: int | None = Field(None, description="Взрослых")
    children: int | None = Field(None, description="Детей")
    pets: bool | None = Field(None, description="Едут с животным")
    budget_total: int | None = Field(None, description="Бюджет на всю поездку на всех, руб.")
    budget_night: int | None = Field(None, description="Лимит цены отеля за ночь, руб., если назван именно он")
    max_travel_hours: float | None = Field(None, description="Максимум часов в дороге в одну сторону")
    transport: str | None = Field(None, description="plane | train, если пользователь выбрал вид транспорта")
    direct_only: bool | None = Field(None, description="Только без пересадок")
    meal: str | None = Field(None, description="breakfast | half_board | all_inclusive")
    free_cancellation: bool | None = Field(None, description="Нужна бесплатная отмена")
    stars_min: int | None = Field(None, description="Минимальная звёздность отеля")
    hotel_wishes: list[str] | None = Field(None, description="Коды удобств: pool, kids_club, spa, gym, parking, "
                                           "pets, beach_line, kitchen")
    abroad: bool | None = Field(None, description="true — за границу, false — только по России")


PARAM_FIELDS = tuple(TripParams.model_fields)


class TripState(TripParams):
    """Состояние диалога: пожелания плюс то, что ведёт код агента."""

    stage: str = "start"                 # start | destination | plan | cart | booked
    suggested: list[str] = Field(default_factory=list)       # id предложенных направлений
    dest_id: str | None = None           # выбранное направление
    package: str | None = None           # выбранный вариант: optimal | budget | comfort
    hotel_id: str | None = None          # закреплённый пользователем отель
    showing: str | None = None           # что показано для выбора по номеру: destinations | packages | hotels
    hotel_ids_shown: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)     # что агент предположил сам
    last_plan: dict | None = None        # краткая сводка прошлого плана — для «что изменилось»
    order: dict | None = None            # оформленный заказ
    requests: list[str] = Field(default_factory=list)        # запросы после покупки
    act: dict = Field(default_factory=dict)                  # действия последней реплики (выбор, «да», сдвиг)
    pending: str | None = None                               # ждём подтверждения необратимого действия: cancel
    params_changed: bool = False                             # пожелания изменились — пересобрать план

    def params(self) -> TripParams:
        return TripParams.model_validate(self.model_dump(include=set(PARAM_FIELDS)))


class TripUpdate(TripParams):
    new_search: bool | None = Field(None, description="true, если пользователь начинает поиск заново")
    clear: list[str] | None = Field(None, description="Параметры, которые больше не нужно учитывать")
    cheaper: bool | None = Field(None, description="true, если просит дешевле")
    pick: int | None = Field(None, description="Номер выбранного варианта из показанного списка (1, 2, 3)")
    pick_name: str | None = Field(None, description="Название выбранного варианта, если назван не номером")
    confirm: bool | None = Field(None, description="true — согласие оформить/подтвердить, false — отказ")
    shift_days: int | None = Field(None, description="Сдвиг дат: +2 «на два дня позже», -1 «на день раньше»")
    show_hotels: bool | None = Field(None, description="true, если просит другие отели")
    hesitate: bool | None = Field(None, description="true, если сомневается и хочет подумать («давай подумаем», «подожди»)")
    question: str | None = Field(None, description="О чём спрашивает: visa | cancellation | baggage | weather | "
                                 "transfer | pets — если задаёт вопрос, а не меняет условия")
    after_sale: str | None = Field(None, description="После покупки: early_checkin | late_checkout | "
                                   "change_dates | cancel (просит отменить) | cancel_info (спрашивает об условиях)")
