"""Time bands computed from the sunset of the given day in Vicenza.

| band            | interval                                              |
|-----------------|-------------------------------------------------------|
| giorno          | sunrise -> sunset - 30 min                            |
| prima_ora_buio  | sunset - 30 min -> sunset + 60 min                    |
| sera            | sunset + 60 min -> 22:30                              |
| notte_fonda     | 22:30 -> 05:00                                        |
| mattina_buia    | 05:00 -> sunrise (only when sunrise is after 05:00)   |

The PDF draft left a 30-minute gap between "giorno" and "prima ora di buio";
here the twilight band starts 30 minutes before sunset, as in the brief.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from typing import Any
from zoneinfo import ZoneInfo

from astral import LocationInfo
from astral.sun import sun
from dateutil.easter import easter

from model.config import load_config


@dataclass(frozen=True)
class BandInterval:
    band: str
    start: datetime
    end: datetime

    def contains(self, dt: datetime) -> bool:
        return self.start <= dt < self.end


def _tz(cfg: dict[str, Any]) -> ZoneInfo:
    return ZoneInfo(cfg["area"]["timezone"])


def _hhmm(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


@lru_cache(maxsize=1024)
def _sun_cached(d: date, lat: float, lon: float, tz_name: str) -> tuple[datetime, datetime]:
    loc = LocationInfo("area", "", tz_name, lat, lon)
    s = sun(loc.observer, date=d, tzinfo=ZoneInfo(tz_name))
    return s["sunrise"], s["sunset"]


def sun_times(d: date, cfg: dict[str, Any] | None = None) -> tuple[datetime, datetime]:
    """Sunrise and sunset (timezone-aware, local time) for date ``d``."""
    cfg = cfg or load_config()
    c = cfg["area"]["center"]
    return _sun_cached(d, float(c["lat"]), float(c["lon"]), cfg["area"]["timezone"])


def localize(dt: datetime, cfg: dict[str, Any] | None = None) -> datetime:
    """Return ``dt`` in the area timezone (naive values are taken as local)."""
    cfg = cfg or load_config()
    tz = _tz(cfg)
    return dt.replace(tzinfo=tz) if dt.tzinfo is None else dt.astimezone(tz)


def _breakpoints(d: date, cfg: dict[str, Any]) -> dict[str, datetime]:
    tz = _tz(cfg)
    b = cfg["timebands"]["boundaries"]
    sunrise, sunset = sun_times(d, cfg)
    return {
        "deep_night_end": datetime.combine(d, _hhmm(b["deep_night_end"]), tz),
        "sunrise": sunrise,
        "twilight_start": sunset - timedelta(minutes=int(b["twilight_start_before_sunset_min"])),
        "twilight_end": sunset + timedelta(minutes=int(b["twilight_end_after_sunset_min"])),
        "evening_end": datetime.combine(d, _hhmm(b["evening_end"]), tz),
    }


def band_at(dt: datetime, cfg: dict[str, Any] | None = None) -> str:
    """Time band of a datetime (naive datetimes are local time)."""
    cfg = cfg or load_config()
    dt = localize(dt, cfg)
    p = _breakpoints(dt.date(), cfg)
    if dt < p["deep_night_end"]:
        return "notte_fonda"
    if dt < p["sunrise"]:
        return "mattina_buia"
    if dt < p["twilight_start"]:
        return "giorno"
    if dt < p["twilight_end"]:
        return "prima_ora_buio"
    if dt < p["evening_end"]:
        return "sera"
    return "notte_fonda"


def band_intervals(d: date, cfg: dict[str, Any] | None = None) -> list[BandInterval]:
    """Bands covering the calendar day ``d`` (00:00 -> 24:00 local), in order.

    Empty intervals are dropped, e.g. "mattina_buia" when sunrise is before
    05:00 or "sera" if the twilight band reached 22:30 (never at Vicenza).
    """
    cfg = cfg or load_config()
    tz = _tz(cfg)
    p = _breakpoints(d, cfg)
    midnight = datetime.combine(d, time(0, 0), tz)
    next_midnight = datetime.combine(d + timedelta(days=1), time(0, 0), tz)
    cuts = [
        ("notte_fonda", midnight, p["deep_night_end"]),
        ("mattina_buia", p["deep_night_end"], max(p["deep_night_end"], p["sunrise"])),
        ("giorno", max(p["deep_night_end"], p["sunrise"]), p["twilight_start"]),
        ("prima_ora_buio", p["twilight_start"], p["twilight_end"]),
        ("sera", p["twilight_end"], p["evening_end"]),
        ("notte_fonda", max(p["evening_end"], p["twilight_end"]), next_midnight),
    ]
    out: list[BandInterval] = []
    cursor = midnight
    for band, start, end in cuts:
        start = max(start, cursor)
        if end > start:
            out.append(BandInterval(band, start, end))
            cursor = end
    return out


def is_dark(band: str, cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or load_config()
    return bool(cfg["timebands"]["bands"][band].get("dark", False))


def evening_date(dt: datetime, cfg: dict[str, Any] | None = None) -> date:
    """Date of the evening a datetime belongs to (before 05:00 = previous day)."""
    cfg = cfg or load_config()
    dt = localize(dt, cfg)
    deep_end = _hhmm(cfg["timebands"]["boundaries"]["deep_night_end"])
    return dt.date() - timedelta(days=1) if dt.time() < deep_end else dt.date()


def is_holiday(d: date, cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or load_config()
    cal = cfg["calendar"]
    if d.strftime("%m-%d") in set(cal.get("holidays_mmdd", [])):
        return True
    return bool(cal.get("easter_monday_is_holiday")) and d == easter(d.year) + timedelta(days=1)


def day_type(dt: datetime, cfg: dict[str, Any] | None = None) -> str:
    """'weekend' or 'feriale'.

    Saturday, Sunday and holidays are weekend; Friday counts as weekend in the
    evening and night bands. Hours before 05:00 belong to the previous evening.
    """
    cfg = cfg or load_config()
    cal = cfg["calendar"]
    band = band_at(dt, cfg)
    d = evening_date(dt, cfg) if band == "notte_fonda" else localize(dt, cfg).date()
    if d.weekday() in cal["weekend_days"] or is_holiday(d, cfg):
        return "weekend"
    if d.weekday() in cal["weekend_evening_days"] and band in cal["weekend_evening_bands"]:
        return "weekend"
    return "feriale"


def band_time(band: str, d: date | None = None, cfg: dict[str, Any] | None = None) -> datetime:
    """Representative datetime of a band on date ``d`` (standard: config date).

    Uses ``standard.band_times``; if that time falls outside the band on the
    given day, the midpoint of the band's longest interval is used instead.
    """
    cfg = cfg or load_config()
    d = d or date.fromisoformat(cfg["standard"]["reference_date"])
    tz = _tz(cfg)
    wanted = cfg["standard"]["band_times"].get(band)
    if wanted:
        candidate = datetime.combine(d, _hhmm(wanted), tz)
        if band_at(candidate, cfg) == band:
            return candidate
    intervals = [iv for iv in band_intervals(d, cfg) if iv.band == band]
    if not intervals:
        raise ValueError(f"la fascia {band} non esiste il {d.isoformat()}")
    longest = max(intervals, key=lambda iv: iv.end - iv.start)
    return longest.start + (longest.end - longest.start) / 2
