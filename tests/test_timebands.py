"""Tests of the time bands computed from sunset at Vicenza."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from model import timebands as tb

TZ = ZoneInfo("Europe/Rome")
DECEMBER = date(2026, 12, 15)
JUNE = date(2026, 6, 21)


@pytest.mark.parametrize(
    "d, sunset_range, sunrise_range",
    [
        (DECEMBER, ("16:20", "16:40"), ("07:40", "08:00")),
        (JUNE, ("20:55", "21:15"), ("05:20", "05:40")),
    ],
)
def test_sun_times_are_plausible_for_vicenza(d, sunset_range, sunrise_range):
    sunrise, sunset = tb.sun_times(d)
    assert sunset_range[0] <= sunset.strftime("%H:%M") <= sunset_range[1]
    assert sunrise_range[0] <= sunrise.strftime("%H:%M") <= sunrise_range[1]


@pytest.mark.parametrize("d", [DECEMBER, JUNE], ids=["dicembre", "giugno"])
def test_band_boundaries(d):
    sunrise, sunset = tb.sun_times(d)
    minute = timedelta(minutes=1)

    def at(dt):
        return tb.band_at(dt)

    assert at(datetime.combine(d, datetime.min.time(), TZ)) == "notte_fonda"
    assert at(datetime(d.year, d.month, d.day, 4, 59, tzinfo=TZ)) == "notte_fonda"
    assert at(datetime(d.year, d.month, d.day, 5, 1, tzinfo=TZ)) == "mattina_buia"
    assert at(sunrise - minute) == "mattina_buia"
    assert at(sunrise + minute) == "giorno"
    assert at(sunset - timedelta(minutes=31)) == "giorno"
    assert at(sunset - timedelta(minutes=29)) == "prima_ora_buio"
    assert at(sunset + timedelta(minutes=59)) == "prima_ora_buio"
    assert at(sunset + timedelta(minutes=61)) == "sera"
    assert at(datetime(d.year, d.month, d.day, 22, 29, tzinfo=TZ)) == "sera"
    assert at(datetime(d.year, d.month, d.day, 22, 31, tzinfo=TZ)) == "notte_fonda"


@pytest.mark.parametrize("d", [DECEMBER, JUNE, date(2026, 3, 29), date(2026, 10, 25)],
                         ids=["dicembre", "giugno", "ora_legale", "ora_solare"])
def test_intervals_cover_the_day_without_gaps(d):
    intervals = tb.band_intervals(d)
    assert intervals[0].start == datetime.combine(d, datetime.min.time(), TZ)
    assert intervals[-1].end == datetime.combine(d + timedelta(days=1), datetime.min.time(), TZ)
    for prev, nxt in zip(intervals, intervals[1:]):
        assert prev.end == nxt.start
    assert {iv.band for iv in intervals} == set(tb.load_config()["timebands"]["order"])
    # band_at agrees with the intervals, minute by minute (5-minute steps)
    for iv in intervals:
        t = iv.start
        while t < iv.end:
            assert tb.band_at(t) == iv.band, t
            t += timedelta(minutes=5)


def test_no_gap_between_day_and_twilight():
    """The PDF draft left 30 minutes uncovered before sunset; the brief closes it."""
    d = DECEMBER
    _, sunset = tb.sun_times(d)
    bands = [iv.band for iv in tb.band_intervals(d)]
    assert bands.index("prima_ora_buio") == bands.index("giorno") + 1
    giorno = next(iv for iv in tb.band_intervals(d) if iv.band == "giorno")
    assert giorno.end == sunset - timedelta(minutes=30)


def test_naive_datetimes_are_local_time():
    assert tb.band_at(datetime(2026, 11, 18, 20, 0)) == "sera"
    assert tb.band_at(datetime(2026, 11, 18, 19, 0, tzinfo=ZoneInfo("UTC"))) == "sera"


@pytest.mark.parametrize(
    "dt, expected",
    [
        (datetime(2026, 11, 18, 20, 0), "feriale"),   # mercoledì sera
        (datetime(2026, 11, 20, 11, 0), "feriale"),   # venerdì mattina
        (datetime(2026, 11, 20, 20, 0), "weekend"),   # venerdì sera
        (datetime(2026, 11, 21, 2, 0), "weekend"),    # notte tra venerdì e sabato
        (datetime(2026, 11, 22, 11, 0), "weekend"),   # domenica
        (datetime(2026, 11, 23, 2, 0), "weekend"),    # notte tra domenica e lunedì
        (datetime(2026, 11, 24, 2, 0), "feriale"),    # notte tra lunedì e martedì
        (datetime(2026, 12, 8, 11, 0), "weekend"),    # Immacolata
        (datetime(2027, 3, 29, 11, 0), "weekend"),    # lunedì dell'Angelo 2027
    ],
)
def test_day_type(dt, expected):
    assert tb.day_type(dt) == expected


def test_standard_band_times_fall_in_their_band():
    cfg = tb.load_config()
    d = date.fromisoformat(cfg["standard"]["reference_date"])
    assert d.weekday() < 5, "la data di riferimento deve essere feriale"
    assert d.month == 11
    for band in cfg["timebands"]["order"]:
        assert tb.band_at(tb.band_time(band, d)) == band


def test_dark_bands():
    assert not tb.is_dark("giorno")
    assert all(tb.is_dark(b) for b in ("prima_ora_buio", "sera", "notte_fonda", "mattina_buia"))
