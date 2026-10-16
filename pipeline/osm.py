"""OpenStreetMap acquisition: municipal boundary, walk network, features.

Primary path (brief): Overpass through osmnx, trying the endpoints in
``config.yaml -> sources.overpass_endpoints`` in order.

Fallback when Overpass is unreachable: a local PBF extract, read with
pyosmium. The extract is either supplied by hand (``data/manual/osm/``) or
built from the OSM planet on the AWS Open Data registry (``osm-pds`` bucket):
the planet is streamed through ``osmium extract`` and never stored on disk.

Both paths produce the same cached outputs in ``data/raw/osm/``:

* ``boundary.parquet``  municipal boundary (one polygon, EPSG:4326)
* ``walk.osm``          walkable ways (osmnx "walk" filter) as OSM XML
* ``features.parquet``  points, lines and polygons used by the parameters
* ``osm_meta.json``     how and when the data was obtained
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from xml.sax.saxutils import quoteattr

import geopandas as gpd
import networkx as nx
import osmnx as ox
import pandas as pd
import shapely
from shapely.geometry import MultiPolygon, Polygon

from model.config import load_config, resolve
from pipeline.common import RAW, log, now_iso, probe, record_source

OSM_DIR = RAW / "osm"
BOUNDARY = OSM_DIR / "boundary.parquet"
WALK_XML = OSM_DIR / "walk.osm"
FEATURES = OSM_DIR / "features.parquet"
META = OSM_DIR / "osm_meta.json"

# Way tags kept on graph edges (osmnx settings.useful_tags_way)
WAY_TAGS = [
    "access", "area", "bridge", "covered", "est_width", "foot", "footway", "highway", "incline", "indoor",
    "junction", "landuse", "lanes", "layer", "lit", "maxspeed", "motorroad", "name", "oneway", "ref", "service",
    "sidewalk", "sidewalk:both", "sidewalk:left", "sidewalk:right", "smoothness", "surface", "tunnel",
    "wheelchair", "width",
]

# Tags kept as columns of the features table
FEATURE_KEYS = [
    "name", "highway", "lit", "shop", "amenity", "opening_hours", "public_transport", "railway", "bus",
    "train", "shelter", "bench", "covered", "tunnel", "layer", "barrier", "landuse", "leisure", "natural",
    "building", "building:levels", "place", "boundary", "admin_level", "wheelchair", "kerb", "footway", "sidewalk", "surface",
    "access", "service", "area", "healthcare", "social_facility", "operator", "ref", "population",
]

BARRIER_LINES = {"wall", "hedge", "fence", "retaining_wall", "city_wall"}
RAIL_LINES = {"rail", "light_rail", "tram", "narrow_gauge", "subway", "funicular"}
POINT_HIGHWAY = {"street_lamp", "bus_stop", "platform", "crossing", "elevator"}
POINT_RAILWAY = {"station", "halt", "tram_stop", "platform", "stop"}
AREA_KEYS = ("landuse", "leisure", "amenity", "shop", "building", "place", "natural", "public_transport")
NATURAL_AREAS = {"wood", "scrub", "grassland", "heath", "water", "wetland"}


# --------------------------------------------------------------------------- #
# osmnx "walk" filter, replicated for the local path
# --------------------------------------------------------------------------- #
_WALK_EXCLUDE = re.compile(
    r"abandoned|bus_guideway|construction|cycleway|motor|no|planned|platform|proposed|raceway|razed|rest_area|services"
)


def _has_sidewalk(tags: dict[str, str]) -> bool:
    if tags.get("sidewalk") in {"both", "left", "right", "yes"}:
        return True
    return any(tags.get(f"sidewalk:{side}") == "yes" for side in ("both", "left", "right"))


def italian_road_rule(tags: dict[str, str]) -> bool:
    """False for roads closed to pedestrians by the Italian highway code.

    ``motorroad=yes`` and ``highway=trunk`` (in Italy: "strada extraurbana
    principale", art. 175 CdS: no pedestrians) are excluded unless the way
    has sidewalks or explicit foot access. osmnx does not apply this rule.
    """
    if tags.get("motorroad") == "yes":
        return False
    if tags.get("highway") in {"trunk", "trunk_link"}:
        return tags.get("foot") in {"yes", "designated", "permissive"} or _has_sidewalk(tags)
    return True


def is_walkable(tags: dict[str, str], italian_rule: bool = True) -> bool:
    """Python equivalent of osmnx's Overpass filter for network_type='walk'."""
    highway = tags.get("highway")
    if not highway or _WALK_EXCLUDE.search(highway):
        return False
    checks = {
        "area": "yes", "access": "private", "foot": "no", "service": "private", "sidewalk": "separate",
        "sidewalk:both": "separate", "sidewalk:left": "separate", "sidewalk:right": "separate",
    }
    if any(key in tags and re.search(pattern, tags[key]) for key, pattern in checks.items()):
        return False
    return italian_road_rule(tags) if italian_rule else True


def _feature_kind(tags: dict[str, str]) -> bool:
    if tags.get("highway") in POINT_HIGHWAY or tags.get("railway") in POINT_RAILWAY:
        return True
    if any(k in tags for k in ("public_transport", "shop", "amenity", "leisure", "landuse", "place")):
        return True
    if tags.get("barrier") in BARRIER_LINES or tags.get("natural") in NATURAL_AREAS:
        return True
    if tags.get("boundary") == "administrative":
        return True
    return False


def _subset(tags: dict[str, str]) -> dict[str, str]:
    return {k: tags[k] for k in FEATURE_KEYS if k in tags}


# --------------------------------------------------------------------------- #
# Local PBF path
# --------------------------------------------------------------------------- #
def local_pbf_path(cfg: dict[str, Any]) -> Path | None:
    for key in ("manual_osm_pbf", "local_osm_pbf"):
        p = resolve(cfg["sources"][key])
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def build_planet_extract(cfg: dict[str, Any]) -> Path:
    """Stream the AWS planet through ``osmium extract`` (about 25-60 minutes)."""
    if not shutil.which("osmium"):
        raise RuntimeError("serve osmium-tool (apt install osmium-tool) per estrarre Vicenza dal planet")
    out = resolve(cfg["sources"]["local_osm_pbf"])
    out.parent.mkdir(parents=True, exist_ok=True)
    bbox = ",".join(str(v) for v in cfg["area"]["extract_bbox"])
    url = cfg["sources"]["planet_url"]
    log.info("estraggo %s dal planet %s (streaming, nessun file intermedio)", bbox, url)
    stream = subprocess.Popen([sys.executable, "-m", "pipeline.planet_stream", url], stdout=subprocess.PIPE)
    extract = subprocess.run(
        ["osmium", "extract", "-s", "simple", "-b", bbox, "-F", "pbf", "-", "-o", str(out), "--overwrite"],
        stdin=stream.stdout, check=False,
    )
    stream.stdout.close()
    stream.wait()
    if extract.returncode != 0 or stream.returncode != 0:
        raise RuntimeError("estrazione dal planet fallita")
    sidecar = {"source": url, "bbox": cfg["area"]["extract_bbox"], "osm_timestamp": planet_timestamp(url),
               "extracted_at": now_iso(), "tool": "pipeline.planet_stream | osmium extract -s simple"}
    out.with_suffix(out.suffix + ".json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return out


def _header_timestamp(path: Path) -> str | None:
    import osmium

    reader = osmium.io.Reader(str(path), osmium.osm.osm_entity_bits.NOTHING)
    try:
        header = reader.header()
        return header.get("osmosis_replication_timestamp") or header.get("timestamp") or None
    finally:
        reader.close()


def planet_timestamp(url: str) -> str | None:
    """Replication timestamp of the remote planet, read from its first 256 kB."""
    import tempfile

    import requests

    resp = requests.get(url, headers={"Range": "bytes=0-262143"}, timeout=60)
    resp.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".osm.pbf") as tmp:
        tmp.write(resp.content)
        tmp.flush()
        try:
            return _header_timestamp(Path(tmp.name))
        except Exception:  # noqa: BLE001 - truncated file: header may still be unreadable
            return None


def pbf_timestamp(path: Path) -> str | None:
    """OSM data timestamp of an extract (header, or sidecar written at extraction)."""
    sidecar = path.with_suffix(path.suffix + ".json")
    if sidecar.exists():
        return json.loads(sidecar.read_text(encoding="utf-8")).get("osm_timestamp")
    return _header_timestamp(path)


def read_local_pbf(path: Path, cfg: dict[str, Any]) -> tuple[gpd.GeoDataFrame, list[dict], gpd.GeoDataFrame]:
    """Single pass over a PBF extract: boundary candidates, walk ways, features."""
    import osmium
    from osmium.geom import WKBFactory

    wkb = WKBFactory()
    italian_rule = bool(cfg["network"].get("italian_road_rule", True))
    walk_ways: list[dict] = []
    records: list[dict] = []
    n_obj = 0
    fp = osmium.FileProcessor(str(path)).with_locations().with_areas()
    for obj in fp:
        n_obj += 1
        if obj.is_relation():
            continue
        tags = {t.k: t.v for t in obj.tags}
        if not tags:
            continue
        if obj.is_node():
            if _feature_kind(tags):
                records.append({"element": "node", "osmid": obj.id, "wkb": wkb.create_point(obj), **_subset(tags)})
        elif obj.is_way():
            if is_walkable(tags, italian_rule=italian_rule):
                try:
                    nodes = [(n.ref, n.location.lon, n.location.lat) for n in obj.nodes]
                except osmium.InvalidLocationError:
                    continue  # way crossing the extract edge, far from the area
                walk_ways.append({"id": obj.id, "nodes": nodes, "tags": {k: tags[k] for k in WAY_TAGS if k in tags}})
            if tags.get("barrier") in BARRIER_LINES or tags.get("railway") in RAIL_LINES:
                try:
                    records.append({"element": "way", "osmid": obj.id, "wkb": wkb.create_linestring(obj), **_subset(tags)})
                except (osmium.InvalidLocationError, RuntimeError):
                    pass
        elif obj.is_area():
            if not (_feature_kind(tags) or "building" in tags):
                continue
            if obj.from_way() and tags.get("barrier") in BARRIER_LINES and not any(k in tags for k in AREA_KEYS):
                continue  # closed barrier ways are kept as lines
            try:
                geom = wkb.create_multipolygon(obj)
            except (osmium.InvalidLocationError, RuntimeError):
                continue
            records.append({"element": "way" if obj.from_way() else "relation", "osmid": obj.orig_id(),
                            "wkb": geom, **_subset(tags)})
    log.info("letti %d oggetti OSM: %d vie pedonali, %d elementi utili", n_obj, len(walk_ways), len(records))
    df = pd.DataFrame.from_records(records)
    geoms = shapely.from_wkb(df.pop("wkb").to_numpy(), on_invalid="ignore")
    feats = gpd.GeoDataFrame(df, geometry=geoms, crs="EPSG:4326")
    feats = feats[~feats.geometry.isna()].copy()
    boundaries = feats[(feats.get("boundary") == "administrative") & feats.geom_type.isin(["Polygon", "MultiPolygon"])].copy()
    return boundaries, walk_ways, feats


def select_municipality(boundaries: gpd.GeoDataFrame, cfg: dict[str, Any]) -> gpd.GeoDataFrame:
    name = cfg["area"]["name"]
    level = str(cfg["area"]["osm_admin_level"])
    cand = boundaries[(boundaries["admin_level"].astype(str) == level) & (boundaries["name"] == name)]
    if cand.empty:
        raise RuntimeError(f"confine comunale di {name} (admin_level={level}) non trovato nei dati OSM")
    cand = cand.assign(_area=cand.to_crs(cfg["area"]["crs_metric"]).area).sort_values("_area", ascending=False)
    out = cand.head(1)[["element", "osmid", "name", "admin_level", "geometry"]].reset_index(drop=True)
    return out


def write_walk_xml(walk_ways: list[dict], path: Path) -> int:
    """Write walkable ways as OSM XML readable by ``osmnx.graph_from_xml``."""
    nodes: dict[int, tuple[float, float]] = {}
    for way in walk_ways:
        for ref, lon, lat in way["nodes"]:
            nodes[ref] = (lon, lat)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<osm version="0.6" generator="quartieri-vivi">\n')
        for ref, (lon, lat) in nodes.items():
            fh.write(f'  <node id="{ref}" lat="{lat:.7f}" lon="{lon:.7f}"/>\n')
        for way in walk_ways:
            fh.write(f'  <way id="{way["id"]}">\n')
            for ref, _, _ in way["nodes"]:
                fh.write(f'    <nd ref="{ref}"/>\n')
            for k, v in way["tags"].items():
                fh.write(f"    <tag k={quoteattr(k)} v={quoteattr(v)}/>\n")
            fh.write("  </way>\n")
        fh.write("</osm>\n")
    return len(nodes)


def acquire_local(cfg: dict[str, Any], pbf: Path) -> dict[str, Any]:
    boundaries, walk_ways, feats = read_local_pbf(pbf, cfg)
    municipality = select_municipality(boundaries, cfg)
    area_buffer = municipality.to_crs(cfg["area"]["crs_metric"]).buffer(1000).to_crs("EPSG:4326").iloc[0]
    feats = feats[feats.intersects(area_buffer)].copy()
    municipality.to_parquet(BOUNDARY, index=False)
    feats.to_parquet(FEATURES, index=False)
    n_nodes = write_walk_xml(walk_ways, WALK_XML)
    return {"n_walk_ways": len(walk_ways), "n_walk_nodes": n_nodes, "n_features": len(feats),
            "osm_timestamp": pbf_timestamp(pbf), "pbf": str(pbf.relative_to(resolve(".")))}


# --------------------------------------------------------------------------- #
# Overpass path
# --------------------------------------------------------------------------- #
def overpass_endpoint(cfg: dict[str, Any]) -> str | None:
    for endpoint in cfg["sources"]["overpass_endpoints"]:
        ok, detail = probe(f"{endpoint}/status")
        log.info("Overpass %s: %s", endpoint, detail)
        if ok:
            return endpoint
    return None


def _configure_osmnx(endpoint: str | None = None) -> None:
    ox.settings.useful_tags_way = WAY_TAGS
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(OSM_DIR / "osmnx_cache")
    ox.settings.requests_timeout = float(load_config()["sources"].get("overpass_timeout_s", 300))
    ox.settings.http_user_agent = load_config()["sources"]["user_agent"]
    if endpoint:
        ox.settings.overpass_url = endpoint


def acquire_overpass(cfg: dict[str, Any], endpoint: str) -> dict[str, Any]:
    _configure_osmnx(endpoint)
    west, south, east, north = cfg["area"]["extract_bbox"]
    admin = ox.features_from_bbox((west, south, east, north), tags={"boundary": "administrative"})
    admin = admin.reset_index().rename(columns={"id": "osmid"})
    municipality = select_municipality(admin[admin.geom_type.isin(["Polygon", "MultiPolygon"])], cfg)
    polygon = municipality.geometry.iloc[0]
    area_buffer = municipality.to_crs(cfg["area"]["crs_metric"]).buffer(1000).to_crs("EPSG:4326").iloc[0]
    G = ox.graph_from_polygon(area_buffer, network_type="walk", simplify=False, retain_all=True, truncate_by_edge=True)
    tags = {
        "highway": list(POINT_HIGHWAY), "railway": list(POINT_RAILWAY | RAIL_LINES), "public_transport": True,
        "shop": True, "amenity": True, "leisure": True, "landuse": True, "barrier": list(BARRIER_LINES),
        "place": True, "natural": list(NATURAL_AREAS), "building": True, "boundary": "administrative",
    }
    feats = ox.features_from_polygon(area_buffer, tags=tags).reset_index().rename(columns={"id": "osmid"})
    keep = ["element", "osmid", "geometry"] + [k for k in FEATURE_KEYS if k in feats.columns]
    feats = gpd.GeoDataFrame(feats[keep], geometry="geometry", crs="EPSG:4326")
    municipality.to_parquet(BOUNDARY, index=False)
    feats.to_parquet(FEATURES, index=False)
    ox.io.save_graphml(G, OSM_DIR / "walk_overpass.graphml")
    _ = polygon
    return {"n_features": len(feats), "osm_timestamp": now_iso(), "overpass_endpoint": endpoint}


# --------------------------------------------------------------------------- #
# Entry points
# --------------------------------------------------------------------------- #
def acquire(cfg: dict[str, Any] | None = None, *, force: bool = False, allow_planet: bool = False) -> dict[str, Any]:
    """Download (or reuse from cache) OSM data for the study area."""
    cfg = cfg or load_config()
    OSM_DIR.mkdir(parents=True, exist_ok=True)
    if not force and META.exists() and BOUNDARY.exists() and FEATURES.exists():
        meta = json.loads(META.read_text(encoding="utf-8"))
        log.info("OSM: uso la cache (%s, dati del %s)", meta.get("method"), meta.get("osm_timestamp"))
        return meta

    endpoint = overpass_endpoint(cfg)
    if endpoint:
        info = acquire_overpass(cfg, endpoint)
        meta = {"method": "overpass", "source": endpoint, **info}
    else:
        record_source("osm_overpass", status="non raggiungibile", url=cfg["sources"]["overpass_endpoints"],
                      detail="nessun endpoint Overpass ha risposto; uso l'estratto locale")
        pbf = local_pbf_path(cfg)
        if pbf is None:
            if not allow_planet:
                raise RuntimeError(
                    "Overpass non raggiungibile e nessun estratto locale. Rilancia con --planet per estrarre "
                    "Vicenza dal planet OSM su AWS, oppure metti un file .osm.pbf in data/manual/osm/vicenza.osm.pbf"
                )
            pbf = build_planet_extract(cfg)
        info = acquire_local(cfg, pbf)
        source = cfg["sources"]["planet_url"] if "raw" in str(pbf) else str(pbf)
        meta = {"method": "local_pbf", "source": source, **info}
    meta["downloaded_at"] = now_iso()
    META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    record_source("osm", status="ok", **meta)
    return meta


def load_boundary() -> gpd.GeoDataFrame:
    return gpd.read_parquet(BOUNDARY)


def load_features() -> gpd.GeoDataFrame:
    return gpd.read_parquet(FEATURES)


def load_walk_graph(cfg: dict[str, Any] | None = None) -> nx.MultiDiGraph:
    """Unsimplified walk graph clipped to the municipality (osmnx conventions)."""
    cfg = cfg or load_config()
    _configure_osmnx()
    meta = json.loads(META.read_text(encoding="utf-8"))
    if meta["method"] == "overpass":
        G = ox.io.load_graphml(OSM_DIR / "walk_overpass.graphml")
        if cfg["network"].get("italian_road_rule", True):
            drop = [(u, v, k) for u, v, k, d in G.edges(keys=True, data=True)
                    if not italian_road_rule({t: d[t] for t in ("highway", "motorroad", "foot", "sidewalk", "sidewalk:both",
                                                                "sidewalk:left", "sidewalk:right") if isinstance(d.get(t), str)})]
            G.remove_edges_from(drop)
    else:
        G = ox.graph_from_xml(WALK_XML, bidirectional=True, simplify=False, retain_all=True)
    polygon = load_boundary().geometry.iloc[0]
    if isinstance(polygon, (Polygon, MultiPolygon)):
        G = ox.truncate.truncate_graph_polygon(G, polygon, truncate_by_edge=True)
    if not cfg["network"]["retain_all"]:
        G = ox.truncate.largest_component(G, strongly=False)
    return G
