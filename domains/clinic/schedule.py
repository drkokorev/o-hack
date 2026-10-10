"""Врачи, расписание и записи. После 13 окт сюда добавится адаптер под данные или API МИС от DBI."""

from __future__ import annotations

import zlib
from datetime import date, datetime, time, timedelta

from pydantic import BaseModel

from core.ru import WEEKDAYS_DAT_PL, fmt_date_long, join_and

SPECIALTIES = [
    "терапевт", "стоматолог", "оториноларинголог", "офтальмолог",
    "невролог", "кардиолог", "дерматолог", "педиатр",
]
_SPECIALTY_ALIASES = {
    "лор": "оториноларинголог",
    "отоларинголог": "оториноларинголог",
    "ухо-горло-нос": "оториноларинголог",
    "окулист": "офтальмолог",
    "глазной": "офтальмолог",
    "зубной": "стоматолог",
    "дантист": "стоматолог",
    "детский врач": "педиатр",
    "врач общей практики": "терапевт",
}


def normalize_specialty(raw: str) -> str | None:
    key = raw.strip().lower().replace("ё", "е")
    if key in _SPECIALTY_ALIASES:
        return _SPECIALTY_ALIASES[key]
    # «к терапевту», «стоматологу» — сравниваем по основе слова
    return next((s for s in SPECIALTIES if key.startswith(s[:-1]) or s.startswith(key)), None)


def _norm(text: str) -> str:
    return text.lower().replace("ё", "е")


class Doctor(BaseModel):
    id: str
    name: str          # «Фамилия Имя Отчество»
    specialty: str
    branch: str
    weekdays: list[int]
    start_hour: int
    end_hour: int
    slot_minutes: int = 30

    @property
    def surname(self) -> str:
        return self.name.split()[0]

    def describe(self) -> str:
        days = join_and([WEEKDAYS_DAT_PL[d] for d in self.weekdays])
        return (f"{self.specialty.capitalize()} {self.name} принимает по {days} "
                f"с {self.start_hour} до {self.end_hour} часов, {self.branch}")


class Slot(BaseModel):
    doctor_id: str
    doctor_name: str
    specialty: str
    branch: str
    start: datetime

    def spoken(self) -> str:
        return f"{fmt_date_long(self.start.date())} в {self.start:%H:%M}, {self.specialty} {self.doctor_name}, {self.branch}"


class Booking(BaseModel):
    id: str
    slot: Slot
    patient_name: str


class SlotTakenError(Exception):
    pass


DOCTORS = [
    Doctor(id="d1", name="Белова Анна Сергеевна", specialty="терапевт", branch="филиал на Лесной", weekdays=[0, 2, 4], start_hour=9, end_hour=15),
    Doctor(id="d2", name="Ковалёв Игорь Павлович", specialty="терапевт", branch="филиал на Садовой", weekdays=[1, 3, 5], start_hour=12, end_hour=20),
    Doctor(id="d3", name="Миронова Елена Викторовна", specialty="стоматолог", branch="филиал на Лесной", weekdays=[0, 1, 2, 3], start_hour=10, end_hour=18),
    Doctor(id="d4", name="Гусев Олег Андреевич", specialty="стоматолог", branch="филиал на Садовой", weekdays=[2, 4, 5], start_hour=9, end_hour=14),
    Doctor(id="d5", name="Яковлева Марина Олеговна", specialty="оториноларинголог", branch="филиал на Лесной", weekdays=[1, 3], start_hour=9, end_hour=13),
    Doctor(id="d6", name="Соколов Денис Игоревич", specialty="офтальмолог", branch="филиал на Садовой", weekdays=[0, 3], start_hour=14, end_hour=20),
    Doctor(id="d7", name="Лебедева Ольга Николаевна", specialty="невролог", branch="филиал на Лесной", weekdays=[1, 4], start_hour=10, end_hour=16),
    Doctor(id="d8", name="Орлов Сергей Михайлович", specialty="кардиолог", branch="филиал на Садовой", weekdays=[0, 2], start_hour=9, end_hour=13),
    Doctor(id="d9", name="Фёдорова Ирина Алексеевна", specialty="дерматолог", branch="филиал на Лесной", weekdays=[2, 4], start_hour=13, end_hour=19),
    Doctor(id="d10", name="Никитин Павел Романович", specialty="педиатр", branch="филиал на Садовой", weekdays=[0, 1, 2, 3, 4], start_hour=8, end_hour=14),
]


class Schedule:
    def __init__(self, doctors: list[Doctor], today: date, horizon_days: int = 14, busy_share: float = 0.45):
        self.doctors = {d.id: d for d in doctors}
        self.today = today
        self.horizon_days = horizon_days
        self.busy_share = busy_share
        self.bookings: dict[str, Booking] = {}
        self._by_slot: dict[tuple[str, datetime], str] = {}
        self._next_id = 1

    def find_doctor(self, name: str) -> Doctor | None:
        """Ищет по фамилии в любом падеже и порядке слов: «к Беловой», «Анна Белова»."""
        for word in _norm(name).split():
            stem = word[:5]
            if len(stem) < 4:
                continue
            for d in self.doctors.values():
                if _norm(d.surname).startswith(stem):
                    return d
        return None

    def doctors_for(self, specialty: str | None) -> list[Doctor]:
        return [d for d in self.doctors.values() if specialty is None or d.specialty == specialty]

    def is_busy(self, doctor_id: str, start: datetime) -> bool:
        if (doctor_id, start) in self._by_slot:
            return True
        # Детерминированная «занятость» мока: одинакова между запусками
        return zlib.crc32(f"{doctor_id}{start:%Y%m%d%H%M}".encode()) % 100 < self.busy_share * 100

    def find(
        self,
        *,
        specialty: str | None = None,
        doctor_id: str | None = None,
        day: date | None = None,
        time_from: time | None = None,
        time_to: time | None = None,
        limit: int = 3,
    ) -> list[Slot]:
        days = [day] if day else [self.today + timedelta(days=i) for i in range(1, self.horizon_days + 1)]
        slots: list[Slot] = []
        for d in days:
            if not self.today < d <= self.today + timedelta(days=self.horizon_days):
                continue
            for doc in self.doctors.values():
                if (doctor_id and doc.id != doctor_id) or (specialty and doc.specialty != specialty):
                    continue
                if d.weekday() not in doc.weekdays:
                    continue
                t, end = datetime.combine(d, time(doc.start_hour)), datetime.combine(d, time(doc.end_hour))
                while t < end:
                    if ((time_from is None or t.time() >= time_from)
                            and (time_to is None or t.time() < time_to)
                            and not self.is_busy(doc.id, t)):
                        slots.append(Slot(doctor_id=doc.id, doctor_name=doc.name, specialty=doc.specialty,
                                          branch=doc.branch, start=t))
                    t += timedelta(minutes=doc.slot_minutes)
        slots.sort(key=lambda s: s.start)
        return slots[:limit]

    def book(self, slot: Slot, patient_name: str) -> Booking:
        if self.is_busy(slot.doctor_id, slot.start):
            raise SlotTakenError(slot.spoken())
        booking = Booking(id=f"B{self._next_id:04d}", slot=slot, patient_name=patient_name)
        self._next_id += 1
        self._store(booking)
        return booking

    def cancel(self, booking_id: str) -> Booking:
        booking = self.bookings.pop(booking_id)
        del self._by_slot[(booking.slot.doctor_id, booking.slot.start)]
        return booking

    def reschedule(self, booking_id: str, slot: Slot) -> Booking:
        if self.is_busy(slot.doctor_id, slot.start):
            raise SlotTakenError(slot.spoken())
        old = self.cancel(booking_id)
        moved = old.model_copy(update={"slot": slot})
        self._store(moved)
        return moved

    def find_bookings(self, *, booking_id: str | None = None, patient_name: str | None = None) -> list[Booking]:
        if booking_id:
            found = [self.bookings[booking_id]] if booking_id in self.bookings else []
        elif patient_name:
            # «Иван Иванов» и «Иванов Иван» — один и тот же пациент
            query = set(_norm(patient_name).split())
            found = [b for b in self.bookings.values()
                     if query <= set(_norm(b.patient_name).split()) or set(_norm(b.patient_name).split()) <= query]
        else:
            found = []
        return sorted(found, key=lambda b: b.slot.start)

    def _store(self, booking: Booking) -> None:
        self.bookings[booking.id] = booking
        self._by_slot[(booking.slot.doctor_id, booking.slot.start)] = booking.id


DEMO_PATIENTS = {"Иванов Иван": "терапевт", "Смирнова Анна": "стоматолог", "Петров Сергей": "кардиолог"}


def seed_demo_bookings(schedule: Schedule) -> None:
    """Существующие записи, чтобы на демо можно было проверить статус, перенос и отмену."""
    for patient, specialty in DEMO_PATIENTS.items():
        slots = schedule.find(specialty=specialty, limit=1)
        if slots:
            schedule.book(slots[0], patient)
