"""Параметры поездки, состояние диалога и то, что извлекается из одной реплики."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from pydantic import BaseModel, Field, field_validator


class RoomAllocation(BaseModel):
    adults: int = Field(ge=1, le=6)
    children_ages: list[Annotated[int, Field(ge=0, le=17)]] = Field(default_factory=list, max_length=4)


class StaySegment(BaseModel):
    dest_id: str
    checkin: date
    checkout: date


class TripParams(BaseModel):
    """Пожелания путешественника. Только их видит и заполняет LLM."""

    origin: str | None = Field(None, description="Город вылета в именительном падеже")
    destination: str | None = Field(None, description="Куда едет: город, курорт или страна, если назван")
    country: str | None = Field(None, description="Названная страна, если город ещё не выбран")
    excluded_countries: list[str] | None = Field(None, description="Страны, которые пользователь явно исключил")
    visa_free_requested: bool | None = Field(None, description="Пользователь хочет безвизовый въезд; актуальные условия не подтверждены")
    trip_types: list[str] | None = Field(None, description="Коды типа отдыха: sea, beach, warm, mountains, ski, "
                                         "city, culture, nature, food, spa, exotic, surf")
    month: int | None = Field(None, ge=1, le=12, description="Месяц поездки 1–12, если точных дат нет")
    season: str | None = Field(None, description="Время года без указанного месяца: summer, autumn, winter, spring")
    year: int | None = Field(None, ge=1, le=9999, description="Год поездки, только если пользователь явно его назвал")
    month_part: str | None = Field(None, description="early | mid | late — «в начале/середине/конце месяца»")
    date_from: date | None = Field(None, description="Дата начала поездки YYYY-MM-DD")
    date_to: date | None = Field(None, description="Дата окончания поездки YYYY-MM-DD")
    nights: int | None = Field(None, description="Число ночей")
    trip_days_min: int | None = Field(None, ge=1, le=365, description="Минимальная длительность поездки в днях, если явно названа")
    trip_days_max: int | None = Field(None, ge=1, le=365, description="Максимальная длительность поездки в днях, если явно названа")
    party_size: int | None = Field(None, description="Общее число путешественников, если известно; возрастной состав может быть не указан")
    adults: int | None = Field(None, description="Взрослых")
    children: int | None = Field(None, description="Детей")
    children_unknown: bool | None = Field(None, description="Едут дети, но их число не указано")
    children_ages: list[Annotated[int, Field(ge=0, le=17)]] | None = Field(
        None, description="Только явно названный возраст детей в годах; список может быть неполным")
    rooms: int | None = Field(None, ge=1, le=20, description="Явно названное число отдельных номеров в отеле")
    room_allocations: list[RoomAllocation] | None = Field(None, description="Явное распределение взрослых и возрастов детей по номерам")
    split_stays: list[StaySegment] | None = Field(None, description="Два явно заданных периода проживания")
    split_choice: int | None = Field(None, ge=1, le=3, description="Номер выбранной показанной пары отелей")
    pets: bool | None = Field(None, description="Едут с животным")
    lodging: str | None = Field(None, description="tent — палатка или своё размещение; hotel — нужен отель")
    search_scope: str | None = Field(None, description="flight_only, train_only, hotel_only, transfer_only, multi_hotel, split_hotel, operator_tour или trip")
    flight_direction: str | None = Field(None, description="one_way — в одну сторону; round_trip — туда и обратно")
    transfer_from: str | None = Field(None, description="Начало трансфера: airport, station или hotel")
    transfer_to: str | None = Field(None, description="Конец трансфера: airport, station или hotel")
    transfer_time: str | None = Field(None, description="Явно указанное время подачи HH:MM")
    transfer_date: date | None = Field(None, description="Явно указанная дата подачи машины")
    transfer_direction: str | None = Field(None, description="one_way или round_trip")
    budget_total: int | None = Field(None, description="Бюджет на всю поездку на всех, руб.")
    budget_per_person: int | None = Field(None, description="Бюджет на одного путешественника, если явно указан")
    budget_night: int | None = Field(None, description="Лимит цены отеля за ночь, руб., если назван именно он")
    max_travel_hours: float | None = Field(None, description="Максимум часов в дороге в одну сторону")
    prefer_short_travel: bool | None = Field(None, description="Желательно недолго ехать или лететь; без численного ограничения")
    air_min_temp: float | None = Field(None, ge=-60, le=60, description="Явный минимум дневной температуры воздуха, °C")
    air_max_temp: float | None = Field(None, ge=-60, le=60, description="Явный максимум дневной температуры воздуха, °C")
    sea_min_temp: float | None = Field(None, ge=-60, le=60, description="Явный минимум температуры моря, °C")
    sea_max_temp: float | None = Field(None, ge=-60, le=60, description="Явный максимум температуры моря, °C")
    transport: str | None = Field(None, description="plane | train; none — подходящего вида транспорта в прототипе нет")
    seat_class: str | None = Field(None, description="Только явно выбранный класс: эконом, бизнес, первый, купе, плацкарт, сидячий")
    flight_concern: bool | None = Field(None, description="Человек боится летать, но пока не запретил перелёт")
    direct_only: bool | None = Field(None, description="Только без пересадок")
    meal: str | None = Field(None, description="meal_included | breakfast | half_board | all_inclusive")
    free_cancellation: bool | None = Field(None, description="Нужна бесплатная отмена")
    stars_min: int | None = Field(None, description="Минимальная звёздность отеля")
    hotel_wishes: list[str] | None = Field(None, description="Коды удобств: pool, kids_club, spa, gym, parking, "
                                           "pets, beach_line, kitchen, wifi")
    abroad: bool | None = Field(None, description="true — за границу, false — только по России")
    baggage: bool | None = Field(None, description="true, если нужен багаж в самолёте")
    economy: bool | None = Field(None, description="true, если важна низкая цена («недорого», «бюджетно»)")
    tentative_fields: list[str] | None = Field(None, description="Упомянутые как возможные, но ещё не подтверждённые параметры")


PARAM_FIELDS = tuple(TripParams.model_fields)


class TripState(TripParams):
    """Состояние диалога: пожелания плюс то, что ведёт код агента."""

    stage: str = "start"                 # start | destination | plan | cart | payment | booked
    suggested: list[str] = Field(default_factory=list)       # id предложенных направлений
    seen: list[str] = Field(default_factory=list)            # все показанные в этом подборе — «ещё» листает дальше
    dest_id: str | None = None           # выбранное направление
    map_place: dict | None = None         # точная запись города, явно выбранного на карте
    package: str | None = None           # выбранный вариант: optimal | budget | comfort
    hotel_id: str | None = None          # закреплённый пользователем отель
    showing: str | None = None           # что показано для выбора по номеру: destinations | packages | hotels
    hotel_ids_shown: list[str] = Field(default_factory=list)
    origin_inferred: bool = False  # город по IP — предположение, которое можно изменить
    ip_city_hint: str | None = None  # город вне списка доступных отправлений
    real_hotels_shown: list[dict] = Field(default_factory=list)  # источник и ID именно показанных записей
    split_displayed: list[dict] = Field(default_factory=list)  # exact pair IDs and demo prices shown to user
    selected_real_hotel: dict | None = None  # выбранная запись открытого каталога
    assumptions: list[str] = Field(default_factory=list)     # что агент предположил сам
    last_plan: dict | None = None        # краткая сводка прошлого плана — для «что изменилось»
    order: dict | None = None            # оформленный заказ
    requests: list[str] = Field(default_factory=list)        # запросы после покупки
    act: dict = Field(default_factory=dict)                  # действия последней реплики (выбор, «да», сдвиг)
    pending: str | None = None                               # ждём подтверждения: cancel | change
    dates_assumed: bool = False                              # даты выбрал агент (их можно пересчитать)
    past_orders: list[dict] = Field(default_factory=list)    # прошлые заказы, если начата новая поездка
    rejected: list[str] = Field(default_factory=list)        # направления, от которых пользователь отказался
    unclear: bool = False                                    # реплика не дала ни параметров, ни действий
    country_conflict: str | None = None                      # страна не совпала с выбранным городом
    place_country: str | None = None                         # уточнённая страна для неоднозначного названия
    unavailable_origin: str | None = None                    # указанный город отправления отсутствует в демо
    pending_question: str | None = None                      # какой недостающий параметр уточняем
    answered_question: str | None = None                     # на какой вопрос ответил последний шаг — для RAG
    asked_text: str | None = None                            # замаскированная последняя реплика — запрос к RAG
    pending_trip_candidate: dict | None = None                # новое намерение до выбора: новая поездка или изменение
    group_conflict: bool = False                              # состав противоречит названному общему числу
    skipped_questions: list[str] = Field(default_factory=list)  # отложенные пользователем уточнения
    payment_method: str | None = None                        # только демонстрационный способ
    last_view: dict | None = None                            # последний показанный список — повторить при непонятной реплике
    params_changed: bool = False                             # пожелания изменились — пересобрать план

    def params(self) -> TripParams:
        return TripParams.model_validate(self.model_dump(include=set(PARAM_FIELDS)))


class TripUpdate(TripParams):
    evidence: dict[str, str] | None = Field(None, description="Для каждого заполненного поля — дословный фрагмент "
                                            "последней реплики, на котором основано значение: {\"nights\": \"11 дн\", "
                                            "\"origin\": \"из пинзы\"}")
    @field_validator("evidence", mode="before")
    @classmethod
    def _evidence_as_text(cls, value):
        """Модель иногда даёт ссылку списком фрагментов («отель с бассейном», «завтраком») — склеиваем."""
        if not isinstance(value, dict):
            return None
        return {str(k): " ".join(map(str, v)) if isinstance(v, (list, tuple)) else str(v)
                for k, v in value.items() if v is not None}

    landmark: str | None = Field(None, description="Достопримечательность, парк, музей, улица, объект, если назван он, "
                                 "а не город — дословно, как в реплике («Эйфелева башня», «парковка Дайкоку»). "
                                 "Город за него не подставляй")
    new_search: bool | None = Field(None, description="true, если пользователь начинает поиск заново")
    needs_trip_choice: bool | None = Field(None, description="Новое намерение может относиться к новой поездке; определяется правилами")
    resolve_trip_choice: str | None = Field(None, description="Выбор при уточнении: new или edit; определяется правилами")
    clear: list[str] | None = Field(None, description="Параметры, которые больше не нужно учитывать")
    remove_hotel_wishes: list[str] | None = Field(None, description="Удобства, от которых пользователь явно отказался; определяется правилами")
    cheaper: bool | None = Field(None, description="true, если просит дешевле")
    pick: int | None = Field(None, description="Номер выбранного варианта из показанного списка (1, 2, 3)")
    pick_name: str | None = Field(None, description="Название выбранного варианта, если назван не номером")
    confirm: bool | None = Field(None, description="true — согласие оформить/подтвердить, false — отказ")
    shift_days: int | None = Field(None, description="Сдвиг дат: +2 «на два дня позже», -1 «на день раньше»")
    show_hotels: bool | None = Field(None, description="true, если просит другие отели")
    show_real_hotels: bool | None = Field(None, description="true, если просит реальные объекты без модельных цен и условий; определяется правилами")
    search_real_hotels: str | None = Field(None, description="Название отеля для поиска в открытом каталоге; определяется правилами")
    wants_ideas: bool | None = Field(None, description="true, если хочет поехать, но не знает куда («хочу отдохнуть», "
                                     "«куда поехать?», «посоветуй»)")
    more: bool | None = Field(None, description="true, если просит другие варианты направлений («покажи ещё»)")
    back: bool | None = Field(None, description="true, если хочет вернуться к выбору направления")
    unknown_place: str | None = Field(None, description="Город или страна, которых нет в каталоге (служебное поле правил)")
    unknown_origin: str | None = Field(None, description="Город вылета, которого нет в списке (служебное поле правил)")
    country_conflict: str | None = Field(None, description="Указанная страна не совпадает с городом (служебное поле правил)")
    place_country: str | None = Field(None, description="Страна для уточнения географического названия (служебное поле правил)")
    corrected_place: str | None = Field(None, description="Исходное написание места, исправленное по опечатке (служебное поле правил)")
    unsure: bool | None = Field(None, description="true, если человек пока не знает ответ на уточняющий вопрос")
    duration_not_given: bool | None = Field(None, description="true, если человек говорит, что не называл длительность")
    clear_duration: bool | None = Field(None, description="true, если человек явно отказался от прежней короткой длительности")
    payment_method: str | None = Field(None, description="Демонстрационный способ оплаты: card | sbp")
    add_adults: int | None = Field(None, description="Сколько взрослых добавить («ещё один взрослый» → 1)")
    hesitate: bool | None = Field(None, description="true, если сомневается и хочет подумать («давай подумаем», «подожди»)")
    question: str | None = Field(None, description="О чём спрашивает: location | visa | cancellation | meal | baggage | weather | "
                                 "travel | transfer | pets | child_fare | sights | areas | food | safety | local_transport | shopping | nightlife | "
                                 "amenities:<коды> — если спрашивает, а не меняет условия")
    after_sale: str | None = Field(None, description="После покупки: early_checkin | late_checkout | change_dates | "
                                   "cancel (просит отменить) | cancel_info (спрашивает об условиях) | reminder | transfer")
