"""Tests of the parameter computations on a small synthetic network.

Synthetic data exist only here, never in production outputs.
"""

from datetime import date

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, Polygon

from model.config import load_config
from pipeline import osm, params, pois, sources_public

CFG = load_config()
METRIC = CFG["area"]["crs_metric"]
X0, Y0 = gpd.GeoSeries.from_xy([11.5469], [45.5470], crs="EPSG:4326").to_crs(METRIC).iloc[0].coords[0]
REF = date(2026, 11, 18)  # wednesday


def _line(*pts):
    return LineString([(X0 + x, Y0 + y) for x, y in pts])


def _seg(sid, geom, classe, su, sv, **tags):
    row = {"segment_id": sid, "classe": classe, "street_count_u": su, "street_count_v": sv,
           "vicolo_cieco": min(su, sv) <= 1, "lunghezza_m": geom.length, "geometry": geom}
    for t in osm.WAY_TAGS:
        row[f"tag_{t.replace(':', '_')}"] = None
    row.update({f"tag_{k}": v for k, v in tags.items()})
    return row


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):
    segs = [
        _seg("A", _line((0, 0), (100, 0)), "residential", 3, 3, lit="yes", sidewalk="both"),
        _seg("B", _line((0, 8), (100, 8)), "footway", 3, 3),                       # parallel to A
        _seg("C", _line((300, 0), (340, 0)), "footway", 3, 3, tunnel="yes", layer="-1"),
        _seg("D", _line((600, 0), (650, 0)), "service", 3, 1),                    # dead end in a park
        _seg("E", _line((1000, 0), (1100, 0)), "primary", 3, 4, sidewalk="no"),
        _seg("F", _line((1500, 0), (1530, 0)), "footway", 3, 1),                 # dead-end passage
    ]
    segments = gpd.GeoDataFrame(segs, crs=METRIC).to_crs("EPSG:4326")

    def feat(element, osmid, geom, **tags):
        return {"element": element, "osmid": osmid, "geometry": geom, **tags}

    feats = [
        feat("node", 1, Point(X0 + 50, Y0 + 5), shop="bakery", opening_hours="Mo-Sa 09:00-19:30"),
        feat("node", 2, Point(X0 + 60, Y0 - 5), amenity="bar"),                       # default hours 07-24
        feat("node", 3, Point(X0 + 40, Y0 + 20), highway="bus_stop", shelter="yes"),
        feat("node", 4, Point(X0 + 1050, Y0 + 10), amenity="pharmacy", opening_hours="Mo-Fr 08:30-19:30"),
        feat("node", 5, Point(X0 + 1010, Y0 + 5), highway="street_lamp"),
        feat("node", 6, Point(X0 + 1090, Y0 + 5), highway="street_lamp"),
        feat("way", 10, Polygon([(X0 + 580, Y0 - 50), (X0 + 700, Y0 - 50), (X0 + 700, Y0 + 50), (X0 + 580, Y0 + 50)]),
             leisure="park", opening_hours="08:00-20:00"),
        feat("way", 11, Polygon([(X0 - 50, Y0 - 60), (X0 + 150, Y0 - 60), (X0 + 150, Y0 + 60), (X0 - 50, Y0 + 60)]),
             landuse="residential"),
        feat("way", 12, Polygon([(X0 + 950, Y0 - 60), (X0 + 1150, Y0 - 60), (X0 + 1150, Y0 + 60), (X0 + 950, Y0 + 60)]),
             landuse="industrial"),
        feat("way", 13, LineString([(X0 + 300, Y0 + 3), (X0 + 340, Y0 + 3)]), barrier="wall"),
    ]
    features = gpd.GeoDataFrame(feats, crs=METRIC).to_crs("EPSG:4326")
    for k in osm.FEATURE_KEYS:
        if k not in features:
            features[k] = None
    return segments, features


@pytest.fixture(scope="module")
def result(synthetic):
    mp = pytest.MonkeyPatch()
    mp.setattr(sources_public, "record_source", lambda *a, **k: None)
    segments, features = synthetic
    out = params.compute(segments, features, CFG, ref_date=REF, bands=["giorno", "sera", "notte_fonda"])
    mp.undo()
    return out.set_index(["fascia", "segment_id"])


def test_light_from_lit_tag_inheritance_and_lamps(result):
    sera = result.loc["sera"]
    assert sera.loc["A", "x_luce"] == 1.0 and sera.loc["A", "flag_luce"] == "measured"
    assert sera.loc["B", "x_luce"] == 1.0 and sera.loc["B", "flag_luce"] == "proxy"   # inherited from A
    assert sera.loc["E", "flag_luce"] == "proxy"                                        # OSM street lamps
    assert 0 < sera.loc["E", "x_luce"] <= 1
    assert sera.loc["C", "flag_luce"] == "excluded" and np.isnan(sera.loc["C", "x_luce"])


def test_escape_routes(result):
    sera = result.loc["sera"]
    assert sera.loc["A", "x_vie_di_fuga"] == 1.0
    assert sera.loc["D", "x_vie_di_fuga"] == pytest.approx(CFG["params"]["vie_di_fuga"]["dead_end_value"])


def test_path_quality(result):
    sera = result.loc["sera"]
    assert sera.loc["A", "x_percorso"] == pytest.approx(0.9)
    assert sera.loc["B", "x_percorso"] == pytest.approx(1.0)
    assert sera.loc["E", "x_percorso"] == pytest.approx(0.2)
    assert sera.loc["D", "flag_percorso"] == "proxy"  # class default


def test_land_use(result):
    sera = result.loc["sera"]
    assert sera.loc["A", "x_uso_suolo"] == pytest.approx(1.0)
    assert sera.loc["E", "x_uso_suolo"] == pytest.approx(0.0)
    assert sera.loc["D", "x_uso_suolo"] == pytest.approx(0.3)            # park at night
    assert result.loc[("giorno", "D"), "x_uso_suolo"] == pytest.approx(0.5)  # park by day


def test_visibility_and_penalties(result):
    sera = result.loc["sera"]
    assert sera.loc["C", "x_visuale"] < sera.loc["A", "x_visuale"]          # underpass + wall
    assert sera.loc["C", "pen_bloccante"] == pytest.approx(0.3)              # underpass
    assert sera.loc["F", "pen_bloccante"] == pytest.approx(0.3)              # dead-end pedestrian passage
    assert sera.loc["D", "pen_bloccante"] == 0                               # dead-end service road: escape routes only
    assert sera.loc["A", "pen_bloccante"] == 0
    assert sera.loc["D", "pen_parco_buio"] == pytest.approx(0.4)             # park closed at 20:00
    assert result.loc[("giorno", "D"), "pen_parco_buio"] == 0                # no park penalty by day
    assert sera.loc["D", "fattore_penalita"] == pytest.approx(0.6)
    assert sera.loc["C", "fattore_penalita"] == pytest.approx(0.7)


def test_opening_hours_drive_active_frontage(result):
    giorno = result.loc[("giorno", "A"), "x_fronti_attivi"]
    sera = result.loc[("sera", "A"), "x_fronti_attivi"]
    notte = result.loc[("notte_fonda", "A"), "x_fronti_attivi"]
    assert giorno > sera > 0          # bakery closes 19:30, bar open until 24
    assert notte == pytest.approx(sera)  # 23:30: only the bar, as at 20:00
    assert result.loc[("sera", "A"), "flag_fronti_attivi"] == "proxy"  # bar uses default hours


def test_help_points_and_transit(result):
    sera = result.loc["sera"]
    assert sera.loc["A", "x_punti_aiuto"] > 0.8                    # open bar a few metres away
    assert result.loc[("giorno", "E"), "x_punti_aiuto"] > 0.9       # pharmacy open at 11:00
    assert result.loc[("giorno", "A"), "x_trasporto"] == pytest.approx(1.0)
    assert result.loc[("notte_fonda", "A"), "x_trasporto"] == pytest.approx(0.0)  # no buses at night


def test_unmeasurable_parameters_excluded(result):
    for k in ("episodi", "cura", "folla"):
        assert (result[f"flag_{k}"] == "excluded").all()
        assert result[f"x_{k}"].isna().all()


def test_reliability_in_range(result):
    assert ((result["affidabilita"] > 0) & (result["affidabilita"] < 1)).all()


def test_people_proxy_is_normalised_on_the_city_maximum(result):
    assert result["x_persone"].max() <= 1.0
    assert result["x_persone"].max() == pytest.approx(1.0)  # the busiest segment-band of the day
    assert result.loc[("giorno", "A"), "x_persone"] > result.loc[("notte_fonda", "A"), "x_persone"]


def test_walk_filter_matches_osmnx_rules():
    assert osm.is_walkable({"highway": "residential"})
    assert osm.is_walkable({"highway": "footway", "footway": "sidewalk"})
    assert not osm.is_walkable({"highway": "motorway"})
    assert not osm.is_walkable({"highway": "cycleway"})
    assert not osm.is_walkable({"highway": "footway", "access": "private"})
    assert not osm.is_walkable({"highway": "secondary", "sidewalk": "separate"})
    assert not osm.is_walkable({"highway": "path", "foot": "no"})
    assert not osm.is_walkable({"highway": "pedestrian", "area": "yes"})
    # Italian highway code: trunk roads and motorroads are closed to pedestrians
    assert not osm.is_walkable({"highway": "trunk"})
    assert not osm.is_walkable({"highway": "primary", "motorroad": "yes"})
    assert osm.is_walkable({"highway": "trunk", "sidewalk": "both"})
    assert osm.is_walkable({"highway": "trunk"}, italian_rule=False)


def test_opening_hours_parser_and_defaults():
    from datetime import datetime
    assert pois.is_open("Mo-Sa 09:00-19:30", datetime(2026, 11, 18, 11, 0)) is True
    assert pois.is_open("Mo-Sa 09:00-19:30", datetime(2026, 11, 18, 20, 0)) is False
    assert pois.is_open("24/7", datetime(2026, 11, 18, 3, 0)) is True
    assert pois.is_open("orario variabile", datetime(2026, 11, 18, 11, 0)) is None
    df = pd.DataFrame({"opening_hours": [None, "garbage"], "categoria": ["pharmacy", "restaurant"]})
    is_open, measured = pois.open_status(df, datetime(2026, 11, 18, 20, 0))
    assert list(is_open) == [False, True] and not measured.any()
