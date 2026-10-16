"""The Overpass path cannot be exercised from an offline machine: here osmnx's
network calls are replaced with small synthetic objects that have the same
shape as osmnx's outputs, to check that the rest of the pipeline consumes them.
"""

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
import pytest
from shapely.geometry import LineString, Point, box

from model.config import load_config
from pipeline import osm, segments

CFG = load_config()
LON, LAT = 11.5469, 45.5470
D = 0.001  # ~80-110 m


def _xml(path):
    nodes = {1: (0, 0), 2: (1, 0), 3: (2, 0), 4: (1, 1), 5: (3, 0), 6: (1, -1)}
    ways = [
        (10, [1, 2, 3], {"highway": "residential", "name": "Via Prova", "lit": "yes", "sidewalk": "both"}),
        (11, [2, 4], {"highway": "footway", "covered": "yes"}),
        (12, [3, 5], {"highway": "trunk", "name": "Tangenziale"}),          # no pedestrians (Italian rule)
        (13, [2, 6], {"highway": "service", "service": "driveway"}),
    ]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6">\n')
        for nid, (x, y) in nodes.items():
            fh.write(f'<node id="{nid}" lat="{LAT + y * D}" lon="{LON + x * D}"/>\n')
        for wid, refs, tags in ways:
            fh.write(f'<way id="{wid}">' + "".join(f'<nd ref="{r}"/>' for r in refs))
            fh.write("".join(f'<tag k="{k}" v="{v}"/>' for k, v in tags.items()) + "</way>\n")
        fh.write("</osm>\n")


@pytest.fixture
def fake_overpass(tmp_path, monkeypatch):
    xml = tmp_path / "net.osm"
    _xml(xml)
    monkeypatch.setattr(osm, "OSM_DIR", tmp_path)
    monkeypatch.setattr(osm, "BOUNDARY", tmp_path / "boundary.parquet")
    monkeypatch.setattr(osm, "FEATURES", tmp_path / "features.parquet")
    monkeypatch.setattr(osm, "META", tmp_path / "osm_meta.json")
    monkeypatch.setattr(osm, "record_source", lambda *a, **k: None)
    monkeypatch.setattr(osm, "overpass_endpoint", lambda cfg: "https://overpass.example/api")
    area = box(LON - 2 * D, LAT - 2 * D, LON + 4 * D, LAT + 2 * D)

    def geocode(query, by_osmid=False):
        assert by_osmid and query == f"R{CFG['area']['osm_relation_id']}"
        return gpd.GeoDataFrame({"osm_id": [CFG["area"]["osm_relation_id"]]}, geometry=[area], crs="EPSG:4326")

    def graph(polygon, network_type, simplify, retain_all, truncate_by_edge):
        assert network_type == "walk" and not simplify
        return ox.graph_from_xml(xml, bidirectional=True, simplify=False, retain_all=True)

    def features(polygon, tags):
        assert "boundary" not in tags  # never download country/region relations
        idx = pd.MultiIndex.from_tuples([("node", 100), ("node", 101), ("way", 200), ("node", 102)], names=["element", "id"])
        return gpd.GeoDataFrame(
            {"amenity": ["bar", None, None, None], "shop": [None, "bakery", None, None],
             "opening_hours": [None, "Mo-Sa 08:00-19:00", None, None], "landuse": [None, None, "residential", None],
             "place": [None, None, None, "suburb"], "name": [None, None, None, ["Centro", "Center"]]},
            geometry=[Point(LON + D, LAT + 0.0001), Point(LON + 1.5 * D, LAT), area.buffer(0), Point(LON + D, LAT)],
            index=idx, crs="EPSG:4326")

    monkeypatch.setattr(ox, "geocode_to_gdf", geocode)
    monkeypatch.setattr(ox, "graph_from_polygon", graph)
    monkeypatch.setattr(ox, "features_from_polygon", features)
    return tmp_path


def test_overpass_path_produces_pipeline_inputs(fake_overpass):
    meta = osm.acquire(CFG, force=True)
    assert meta["method"] == "overpass"
    boundary = osm.load_boundary()
    assert boundary["osmid"].iloc[0] == CFG["area"]["osm_relation_id"]
    feats = osm.load_features()
    assert {"element", "osmid", "amenity", "shop", "opening_hours"} <= set(feats.columns)
    assert feats.loc[feats["place"] == "suburb", "name"].iloc[0] == "Centro;Center"  # lists flattened

    G = osm.load_walk_graph(CFG)
    highways = {d.get("highway") for _, _, d in G.edges(data=True)}
    assert "trunk" not in highways and "residential" in highways

    segs = segments.build_segments(CFG)
    assert set(segs["classe"]) == {"residential", "footway", "service"}
    via = segs[segs["nome"] == "Via Prova"]
    assert via["tag_lit"].eq("yes").all() and via["lunghezza_m"].sum() == pytest.approx(155, rel=0.05)
