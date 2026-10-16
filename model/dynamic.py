"""Dynamic modifiers for a given date and time (brief, section 7).

* time band and weekday/weekend: ``model.timebands``
* season (parks from October to April): applied in ``pipeline.params``
* weather: Open-Meteo (no key), cached 30 minutes, with a manual override
  ``sereno`` / ``pioggia``. When Open-Meteo cannot be reached the condition is
  ``sereno`` and the response says so (``fonte: default``): weather is never
  invented.
* events: from one hour before to one hour after, within 300 m: people +0.3,
  active frontage +0.2, help points +0.2 (max 1). Real events come from
  ``data/manual/eventi.csv``; the file ``data/demo/eventi_demo.csv`` holds a
  *simulated* scenario for the demo and is used only when ``demo=True``.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from model.config import load_config, param_keys, resolve
from model.timebands import localize

WEATHER_CACHE = Path("data/raw/meteo")
EVENTS_REAL = Path("data/manual/eventi.csv")
EVENTS_DEMO = Path("data/demo/eventi_demo.csv")
CONDITIONS = ("sereno", "pioggia", "nebbia")


# --------------------------------------------------------------------------- #
# Weather
# --------------------------------------------------------------------------- #
def _fetch_open_meteo(day: str, cfg: dict[str, Any]) -> dict[str, Any]:
    import requests

    dcfg = cfg["dynamic"]
    c = cfg["area"]["center"]
    today = datetime.now().date().isoformat()
    url = dcfg["open_meteo_archive_url"] if day < today else dcfg["open_meteo_forecast_url"]
    params = {"latitude": c["lat"], "longitude": c["lon"], "hourly": "precipitation,visibility",
              "timezone": cfg["area"]["timezone"], "start_date": day, "end_date": day}
    resp = requests.get(url, params=params, timeout=float(cfg["sources"]["http_timeout_s"]),
                        headers={"User-Agent": cfg["sources"]["user_agent"]})
    resp.raise_for_status()
    return resp.json()


def weather_at(dt: datetime, override: str | None = None, cfg: dict[str, Any] | None = None,
               fetch=None) -> dict[str, Any]:
    """Weather condition at ``dt``: {'condizione', 'fonte', 'pioggia_mm', 'visibilita_m'}."""
    cfg = cfg or load_config()
    if override:
        if override not in CONDITIONS:
            raise ValueError(f"meteo non valido: {override} (validi: {', '.join(CONDITIONS)})")
        return {"condizione": override, "fonte": "impostato a mano", "pioggia_mm": None, "visibilita_m": None}
    dt = localize(dt, cfg)
    day = dt.date().isoformat()
    cache = resolve(WEATHER_CACHE) / f"open_meteo_{day}.json"
    max_age = float(cfg["dynamic"]["weather_cache_min"]) * 60
    data = None
    if cache.exists() and time.time() - cache.stat().st_mtime < max_age:
        data = json.loads(cache.read_text(encoding="utf-8"))
    else:
        try:
            data = (fetch or _fetch_open_meteo)(day, cfg)
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(data), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 - offline: no invented weather
            return {"condizione": "sereno", "fonte": f"default (Open-Meteo non raggiungibile: {type(exc).__name__})",
                    "pioggia_mm": None, "visibilita_m": None}
    hourly = data.get("hourly", {})
    stamps = hourly.get("time", [])
    key = dt.strftime("%Y-%m-%dT%H:00")
    if key not in stamps:
        return {"condizione": "sereno", "fonte": "default (ora non presente nella risposta Open-Meteo)",
                "pioggia_mm": None, "visibilita_m": None}
    i = stamps.index(key)
    rain = (hourly.get("precipitation") or [None] * len(stamps))[i]
    vis = (hourly.get("visibility") or [None] * len(stamps))[i]
    dcfg = cfg["dynamic"]
    condition = "sereno"
    if rain is not None and rain >= float(dcfg["rain_threshold_mm"]):
        condition = "pioggia"
    elif vis is not None and vis < float(dcfg["fog_visibility_m"]):
        condition = "nebbia"
    return {"condizione": condition, "fonte": "Open-Meteo", "pioggia_mm": rain, "visibilita_m": vis}


def apply_weather(X: np.ndarray, condition: str, cfg: dict[str, Any] | None = None) -> np.ndarray:
    """Rain: people ×0.7 and visibility ×0.8; fog: visibility ×0.8."""
    cfg = cfg or load_config()
    keys = param_keys(cfg)
    X = X.copy()
    if condition == "pioggia":
        X[:, keys.index("persone")] *= cfg["params"]["persone"]["rain_factor"]
        X[:, keys.index("visuale")] *= cfg["params"]["visuale"]["rain_factor"]
    elif condition == "nebbia":
        X[:, keys.index("visuale")] *= cfg["params"]["visuale"]["rain_factor"]
    return X


# --------------------------------------------------------------------------- #
# Events
# --------------------------------------------------------------------------- #
def load_events(demo: bool = False, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """Events with columns titolo, inizio, fine, lat, lon, simulato.

    Real events (``data/manual/eventi.csv``) are always used; the simulated
    demo scenario only when ``demo`` is True.
    """
    cfg = cfg or load_config()
    frames = []
    for path, simulated in ((EVENTS_REAL, False), (EVENTS_DEMO, True)):
        p = resolve(path)
        if not p.exists() or (simulated and not demo):
            continue
        df = pd.read_csv(p)
        df["simulato"] = df.get("simulato", simulated)
        df["simulato"] = df["simulato"].astype(str).str.lower().isin(["true", "1", "si", "sì", "yes"]) | simulated
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["titolo", "inizio", "fine", "lat", "lon", "simulato"])
    out = pd.concat(frames, ignore_index=True)
    tz = cfg["area"]["timezone"]
    for col in ("inizio", "fine"):
        out[col] = pd.to_datetime(out[col]).map(lambda t: t.tz_localize(tz) if t.tzinfo is None else t.tz_convert(tz))
    return out


def active_events(events: pd.DataFrame, dt: datetime, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    """Events whose window (start − 1 h, end + 1 h) contains ``dt``."""
    cfg = cfg or load_config()
    if events.empty:
        return events
    dt = pd.Timestamp(localize(dt, cfg))
    margin = timedelta(minutes=int(cfg["dynamic"]["event_window_min"]))
    return events[(events["inizio"] - margin <= dt) & (dt <= events["fine"] + margin)]


def apply_events(X: np.ndarray, lines_metric, events: pd.DataFrame, cfg: dict[str, Any] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Raise people, active frontage and help points near active events.

    Returns the new matrix and a boolean mask of the segments affected.
    """
    cfg = cfg or load_config()
    X = X.copy()
    hit = np.zeros(X.shape[0], dtype=bool)
    if events.empty:
        return X, hit
    import geopandas as gpd
    from shapely import STRtree

    pts = gpd.GeoSeries.from_xy(events["lon"], events["lat"], crs="EPSG:4326").to_crs(cfg["area"]["crs_metric"])
    pairs = STRtree(np.asarray(lines_metric)).query(pts.values, predicate="dwithin",
                                                    distance=float(cfg["dynamic"]["event_radius_m"]))
    hit[np.unique(pairs[1])] = True
    keys = param_keys(cfg)
    for param, delta in cfg["dynamic"]["event_effects"].items():
        j = keys.index(param)
        X[hit, j] = np.minimum(1.0, np.nan_to_num(X[hit, j], nan=0.0) + float(delta))
    return X, hit
