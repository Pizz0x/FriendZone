"""Weather and events (brief, section 7). Events here are test data only."""

from datetime import datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString

from model import dynamic
from model.config import load_config, param_keys

CFG = load_config()
KEYS = param_keys(CFG)


@pytest.fixture(autouse=True)
def tmp_weather_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(dynamic, "WEATHER_CACHE", tmp_path / "meteo")
    monkeypatch.setattr(dynamic, "EVENTS_REAL", tmp_path / "eventi.csv")
    monkeypatch.setattr(dynamic, "EVENTS_DEMO", tmp_path / "eventi_demo.csv")
    return tmp_path


def _response(rain, vis):
    hours = [f"2026-11-18T{h:02d}:00" for h in range(24)]
    return {"hourly": {"time": hours, "precipitation": [rain] * 24, "visibility": [vis] * 24}}


def test_manual_override_wins():
    w = dynamic.weather_at(datetime(2026, 11, 18, 21), "pioggia", CFG)
    assert w["condizione"] == "pioggia" and w["fonte"] == "impostato a mano"
    with pytest.raises(ValueError):
        dynamic.weather_at(datetime(2026, 11, 18, 21), "grandine", CFG)


def test_open_meteo_parsing_and_cache():
    calls = []

    def fetch(day, cfg):
        calls.append(day)
        return _response(1.2, 20000)

    w = dynamic.weather_at(datetime(2026, 11, 18, 21), None, CFG, fetch=fetch)
    assert w["condizione"] == "pioggia" and w["fonte"] == "Open-Meteo" and w["pioggia_mm"] == 1.2
    w2 = dynamic.weather_at(datetime(2026, 11, 18, 22), None, CFG, fetch=fetch)
    assert w2["condizione"] == "pioggia" and calls == ["2026-11-18"]          # second call served from cache
    fog = dynamic.weather_at(datetime(2026, 11, 19, 7), None, CFG, fetch=lambda d, c: {
        "hourly": {"time": [f"2026-11-19T{h:02d}:00" for h in range(24)], "precipitation": [0.0] * 24,
                   "visibility": [300.0] * 24}})
    assert fog["condizione"] == "nebbia"


def test_offline_weather_is_not_invented():
    def fetch(day, cfg):
        raise ConnectionError("rete bloccata")

    w = dynamic.weather_at(datetime(2026, 11, 18, 21), None, CFG, fetch=fetch)
    assert w["condizione"] == "sereno" and w["fonte"].startswith("default")


def test_rain_lowers_people_and_visibility():
    X = np.full((2, 12), 0.8)
    rain = dynamic.apply_weather(X, "pioggia", CFG)
    assert rain[0, KEYS.index("persone")] == pytest.approx(0.8 * 0.7)
    assert rain[0, KEYS.index("visuale")] == pytest.approx(0.8 * 0.8)
    assert rain[0, KEYS.index("luce")] == pytest.approx(0.8)
    assert np.array_equal(dynamic.apply_weather(X, "sereno", CFG), X)


def _events(path, simulated):
    pd.DataFrame({"titolo": ["Concerto"], "inizio": ["2026-11-18T20:30:00"], "fine": ["2026-11-18T23:00:00"],
                  "lat": [45.5470], "lon": [11.5469], "simulato": [simulated]}).to_csv(path, index=False)


def test_demo_events_only_on_request(tmp_weather_cache):
    _events(tmp_weather_cache / "eventi_demo.csv", True)
    assert dynamic.load_events(demo=False, cfg=CFG).empty
    ev = dynamic.load_events(demo=True, cfg=CFG)
    assert len(ev) == 1 and ev["simulato"].all()


def test_event_window_and_effect(tmp_weather_cache):
    _events(tmp_weather_cache / "eventi.csv", False)
    ev = dynamic.load_events(cfg=CFG)
    assert len(dynamic.active_events(ev, datetime(2026, 11, 18, 19, 45), CFG)) == 1   # one hour before
    assert len(dynamic.active_events(ev, datetime(2026, 11, 18, 23, 55), CFG)) == 1   # one hour after
    assert dynamic.active_events(ev, datetime(2026, 11, 18, 19, 15), CFG).empty
    x0, y0 = gpd.GeoSeries.from_xy([11.5469], [45.5470], crs="EPSG:4326").to_crs(CFG["area"]["crs_metric"]).iloc[0].coords[0]
    lines = [LineString([(x0, y0 + 50), (x0 + 50, y0 + 50)]), LineString([(x0 + 2000, y0), (x0 + 2050, y0)])]
    X = np.full((2, 12), 0.5)
    X[0, KEYS.index("fronti_attivi")] = 0.95
    new, hit = dynamic.apply_events(X, lines, ev, CFG)
    assert hit.tolist() == [True, False]
    assert new[0, KEYS.index("persone")] == pytest.approx(0.8)
    assert new[0, KEYS.index("fronti_attivi")] == pytest.approx(1.0)       # capped at 1
    assert new[0, KEYS.index("punti_aiuto")] == pytest.approx(0.7)
    assert np.array_equal(new[1], X[1])
