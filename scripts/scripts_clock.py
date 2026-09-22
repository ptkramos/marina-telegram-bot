"""Relógio controlável para simulações (arena de modelos).

Substitui `datetime.datetime` e `datetime.date` no próprio módulo `datetime`
ANTES dos imports do bot — todo `from datetime import datetime` passa a ver o
horário do cenário. Dentro de um turno o tempo anda com o relógio real.
"""
import sqlite3
import time


def install_clock(dtmod):
    real_dt, real_date = dtmod.datetime, dtmod.date

    class Clock:
        def __init__(self):
            self.base = real_dt.now()
            self.t0 = time.monotonic()

        def set(self, when):
            self.base = real_dt(*when.timetuple()[:6], when.microsecond)
            self.t0 = time.monotonic()

        def now(self):
            t = self.base + dtmod.timedelta(seconds=time.monotonic() - self.t0)
            return FakeDatetime(*t.timetuple()[:6], t.microsecond)

    class FakeDatetime(real_dt):
        @classmethod
        def now(cls, tz=None):
            t = clock.now()
            return t if tz is None else t.astimezone(tz)

        @classmethod
        def today(cls):
            return clock.now()

        @classmethod
        def utcnow(cls):
            return clock.now().astimezone(dtmod.timezone.utc).replace(tzinfo=None)

    class FakeDate(real_date):
        @classmethod
        def today(cls):
            t = clock.now()
            return FakeDate(t.year, t.month, t.day)

    clock = Clock()
    dtmod.datetime = FakeDatetime
    dtmod.date = FakeDate
    sqlite3.register_adapter(FakeDatetime, lambda v: v.isoformat(" "))
    sqlite3.register_adapter(FakeDate, lambda v: v.isoformat())
    return clock
