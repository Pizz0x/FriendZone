"""Build the two interfaces as self-contained HTML pages.

- ``frontend/enti.html``: the map for the Comune and other bodies (2D, every
  street coloured, choice of hour, day, weather and profile);
- ``frontend/lumi.html``: the citizens' app «Lumi» (3D map, profile from a
  short onboarding, navigator on the least-cost route, reports, support).

Both recompute S in the browser (``frontend/src/core.js``) from parameters
precomputed here for every hour of a weekday and of a Saturday of the
reference week. Data are packed as gzip + base64 typed arrays and decoded
with the browser's DecompressionStream.

    python -m pipeline.frontend            # writes frontend/enti.html, lumi.html, index.html
"""

from __future__ import annotations

import base64
import gzip
import json
from datetime import date, datetime, time, timedelta
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from model import scoring, timebands
from model.config import ROOT, load_config, param_keys, param_labels
from pipeline import osm, params, pois
from pipeline.common import PROCESSED, log, setup_logging
from pipeline.scenario import Engine
from pipeline.validate import LIGHT_SOURCE_LABELS

FRONTEND = ROOT / "frontend"
SRC = FRONTEND / "src"
PAGES = {"enti": FRONTEND / "enti.html", "lumi": FRONTEND / "lumi.html"}
MASCOTS = FRONTEND / "assets" / "lumi"
SCALE = 250.0          # parameter values are stored as round(x * 250); 255 = not available
NA = 255


def _b64(arr: np.ndarray) -> str:
    return base64.b64encode(gzip.compress(np.ascontiguousarray(arr).tobytes(), 9)).decode("ascii")


def _u8(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    out = np.where(np.isnan(x), NA, np.round(np.clip(x, 0, 1) * SCALE))
    return out.astype(np.uint8)


def _orient(segments: gpd.GeoDataFrame) -> tuple[gpd.GeoSeries, np.ndarray, np.ndarray, int]:
    """Geometries turned to run from node u to node v, plus node indices.

    After osmnx makes the graph undirected a geometry may run v -> u. The
    position of each node is the endpoint its segments share most often.
    """
    from collections import Counter, defaultdict

    ends = defaultdict(Counter)
    first = [tuple(np.round(g.coords[0], 6)) for g in segments.geometry]
    last = [tuple(np.round(g.coords[-1], 6)) for g in segments.geometry]
    for a, b, p, q in zip(segments["u"], segments["v"], first, last):
        for node in (a, b):
            ends[node][p] += 1
            ends[node][q] += 1
    where = {node: c.most_common(1)[0][0] for node, c in ends.items()}
    flip = np.array([p != where[a] and p == where[b] for a, b, p in zip(segments["u"], segments["v"], first)])
    geoms = gpd.GeoSeries([shapely.reverse(g) if f else g for g, f in zip(segments.geometry, flip)], crs=segments.crs)
    nodes = {node: k for k, node in enumerate(sorted(where))}
    u = segments["u"].map(nodes).to_numpy(np.int64)
    v = segments["v"].map(nodes).to_numpy(np.int64)
    if len(nodes) > 65535:
        raise ValueError("troppi nodi per l'indice a 16 bit dell'interfaccia")
    return geoms, u, v, len(nodes)


def _geometry(geoms: gpd.GeoSeries, cfg: dict[str, Any]) -> dict[str, str]:
    """Line vertices quantised to 1e-5 degrees, delta-encoded per segment."""
    metric = cfg["area"]["crs_metric"]
    geoms = geoms.to_crs(metric).simplify(1.0).to_crs("EPSG:4326")
    counts, coords = [], []
    for g in geoms:
        parts = [g] if g.geom_type == "LineString" else list(g.geoms)
        pts = np.vstack([np.asarray(p.coords) for p in parts])
        q = np.round(pts * 1e5).astype(np.int64)
        d = np.vstack([q[:1], np.diff(q, axis=0)])
        counts.append(len(q))
        coords.append(d)
    return {"counts": _b64(np.asarray(counts, dtype=np.uint16)),
            "coords": _b64(np.vstack(coords).astype(np.int32).ravel())}


def _polygons_geojson(gdf: gpd.GeoDataFrame, cfg: dict[str, Any], tolerance: float, props: list[str]) -> dict:
    metric = cfg["area"]["crs_metric"]
    g = gdf.to_crs(metric).copy()
    g["geometry"] = g.geometry.simplify(tolerance)
    g = g[~g.geometry.is_empty].to_crs("EPSG:4326")
    data = json.loads(g[props + ["geometry"]].to_json(drop_id=True))

    def rnd(c):
        return [rnd(v) for v in c] if isinstance(c, list) else round(c, 5)
    for f in data["features"]:
        f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
    return data


def _non_walkable_roads(cfg: dict[str, Any], boundary) -> dict:
    """Roads where pedestrians do not walk (motorways, trunk roads, private roads): drawn in grey."""
    import osmium
    from osmium.geom import WKBFactory

    pbf = osm.local_pbf_path(cfg)
    if pbf is None:
        return {"type": "FeatureCollection", "features": []}
    roads = {"motorway", "motorway_link", "trunk", "trunk_link", "primary", "primary_link", "secondary",
             "secondary_link", "tertiary", "tertiary_link", "unclassified", "residential", "service"}
    wkb = WKBFactory()
    lines, kinds = [], []
    fp = osmium.FileProcessor(str(pbf)).with_locations().with_filter(osmium.filter.KeyFilter("highway"))
    for obj in fp:
        if not obj.is_way():
            continue
        tags = {t.k: t.v for t in obj.tags}
        if tags.get("highway") not in roads or osm.is_walkable(tags, cfg["network"].get("italian_road_rule", True)):
            continue
        if tags.get("area") == "yes":
            continue
        try:
            lines.append(shapely.from_wkb(wkb.create_linestring(obj), on_invalid="ignore"))
            kinds.append(tags["highway"])
        except Exception:  # noqa: BLE001 - way crossing the extract edge
            continue
    gdf = gpd.GeoDataFrame({"classe": kinds}, geometry=lines, crs="EPSG:4326")
    gdf = gdf[gdf.intersects(boundary)]
    gdf["geometry"] = gdf.geometry.intersection(boundary)
    gdf = gdf[~gdf.geometry.is_empty & gdf.geom_type.isin(["LineString", "MultiLineString"])]
    return _polygons_geojson(gdf, cfg, 2.0, ["classe"])


# height in metres by OSM building type (OSM has a height or levels for under 1% of
# Vicenza's buildings): only for the 3D picture of the app, never for the score
BUILDING_HEIGHT = {"house": 7, "detached": 7, "semidetached_house": 7, "terrace": 8, "bungalow": 4,
                   "apartments": 15, "residential": 12, "dormitory": 12, "hotel": 15,
                   "church": 16, "cathedral": 30, "chapel": 7, "bell_tower": 30, "basilica": 25,
                   "school": 11, "university": 13, "college": 12, "kindergarten": 5, "hospital": 16, "public": 12,
                   "civic": 12, "government": 12, "office": 13, "commercial": 9, "retail": 7, "supermarket": 7,
                   "industrial": 9, "warehouse": 9, "depot": 8, "train_station": 10, "transportation": 8,
                   "roof": 4, "carport": 3, "hut": 3, "shed": 3, "garage": 3, "garages": 3, "kiosk": 3,
                   "farm_auxiliary": 6, "barn": 7, "greenhouse": 3, "service": 4, "construction": 6, "ruins": 3}


def _building_height(kind: str, levels: float, area: float, in_centre: bool) -> float:
    if levels == levels and levels > 0:  # not NaN
        return levels * 3.2 + 1
    if kind in BUILDING_HEIGHT:
        return BUILDING_HEIGHT[kind]
    if area < 30:
        return 3.5
    if in_centre and area > 60:
        return 13
    return 7 if area < 150 else 10 if area < 800 else 12


def _buildings(feats: gpd.GeoDataFrame, boundary, cfg: dict[str, Any]) -> dict[str, Any]:
    """OSM buildings for the 3D map: rings delta-encoded like the segments, heights in metres."""
    metric = cfg["area"]["crs_metric"]
    b = pois.all_buildings(feats)
    b = b[b.representative_point().within(boundary)].to_crs(metric)
    area = b.area
    b = b[area >= 12].copy()
    b["area"] = b.area
    centre = gpd.GeoSeries.from_xy([11.5469], [45.5470], crs="EPSG:4326").to_crs(metric).iloc[0].buffer(900)
    c = b.representative_point()
    levels = (pd.to_numeric(b["building:levels"], errors="coerce") if "building:levels" in b.columns
              else pd.Series(np.nan, index=b.index))
    b["h"] = [_building_height(str(k), float(lv), a, bool(ic))
              for k, lv, a, ic in zip(b["building"], levels, b["area"], c.within(centre))]
    b["geometry"] = b.geometry.simplify(0.8, preserve_topology=True)
    # spatial order keeps consecutive deltas small, which gzip likes
    b["cell"] = (np.floor(c.x / 250) * 1e5 + np.floor(c.y / 250)).astype(np.int64)
    b = b.sort_values("cell").to_crs("EPSG:4326")
    rings_per, ring_len, heights, chunks = [], [], [], []
    prev = np.zeros(2, dtype=np.int64)
    for geom, h in zip(b.geometry, b["h"]):
        polys = [geom] if geom.geom_type == "Polygon" else list(getattr(geom, "geoms", []))
        for poly in polys:
            if poly.is_empty or poly.geom_type != "Polygon":
                continue
            rings = [poly.exterior] + [r for r in poly.interiors if shapely.Polygon(r).area > 3e-9]
            rings_per.append(len(rings))
            heights.append(min(255, int(round(h))))
            for ring in rings:
                q = np.round(np.asarray(ring.coords)[:-1] * 1e5).astype(np.int64)
                ring_len.append(len(q))
                chunks.append(np.diff(np.vstack([prev, q]), axis=0))
                prev = q[-1]
    log.info("interfaccia: %d edifici, %d vertici", len(heights), sum(ring_len))
    return {"rings": _b64(np.asarray(rings_per, dtype=np.uint8)), "counts": _b64(np.asarray(ring_len, dtype=np.uint16)),
            "coords": _b64(np.vstack(chunks).astype(np.int32).ravel()), "heights": _b64(np.asarray(heights, dtype=np.uint8))}


AMENITY_IT = {"restaurant": "ristorante", "bar": "bar", "cafe": "caffè", "pub": "pub", "fast_food": "fast food",
              "ice_cream": "gelateria", "pharmacy": "farmacia", "hospital": "ospedale", "clinic": "ambulatorio",
              "doctors": "medico", "school": "scuola", "kindergarten": "scuola dell'infanzia", "university": "università",
              "college": "istituto", "library": "biblioteca", "theatre": "teatro", "cinema": "cinema",
              "place_of_worship": "luogo di culto", "police": "polizia", "townhall": "municipio", "post_office": "ufficio postale",
              "bank": "banca", "parking": "parcheggio", "fuel": "distributore", "bus_station": "autostazione",
              "marketplace": "mercato", "arts_centre": "centro culturale", "community_centre": "centro civico",
              "fire_station": "vigili del fuoco", "courthouse": "tribunale", "nightclub": "discoteca"}
LEISURE_IT = {"park": "parco", "garden": "giardino", "playground": "parco giochi", "sports_centre": "centro sportivo",
              "stadium": "stadio", "pitch": "campo sportivo", "fitness_centre": "palestra", "sports_hall": "palazzetto"}
PLACE_IT = {"square": "piazza", "quarter": "quartiere", "neighbourhood": "quartiere", "suburb": "quartiere",
            "village": "frazione", "hamlet": "località", "locality": "località"}
# never offered by the search (brief: no shelters or reception facilities)
_EXCLUDED_NAMES = r"antiviolenz|rifugio|casa delle donne|accoglienza|centro donna"


def _search_index(seg: gpd.GeoDataFrame, feats: gpd.GeoDataFrame, boundary, cfg: dict[str, Any]) -> list[list]:
    """Streets and named places for the app's offline search: [name, detail, lon*1e5, lat*1e5, kind (0 street, 1 place)]."""
    metric = cfg["area"]["crs_metric"]
    unnamed = cfg["network"]["unnamed_label"]
    out: list[list] = []
    s = seg[seg["via"].fillna(unnamed) != unnamed].to_crs(metric)
    for (via, q), g in s.groupby(["via", "quartiere"]):
        longest = g.loc[g["lunghezza_m"].idxmax()].geometry
        p = gpd.GeoSeries([longest.interpolate(0.5, normalized=True)], crs=metric).to_crs("EPSG:4326").iloc[0]
        out.append([via, q, int(round(p.x * 1e5)), int(round(p.y * 1e5)), 0])
    f = feats[feats["name"].notna()].copy()
    f = f[f.representative_point().within(boundary)]
    social = f.get("social_facility", pd.Series(index=f.index, dtype=object)).notna() | f["amenity"].eq("social_facility")
    f = f[~social & ~f["name"].str.contains(_EXCLUDED_NAMES, case=False, regex=True)]
    seen = set()
    for _, r in f.iterrows():
        if r.get("railway") in ("station", "halt") or r.get("public_transport") == "station":
            kind = "stazione"
        elif r.get("highway") == "bus_stop" or r.get("public_transport") == "platform":
            kind = "fermata del bus"
        elif isinstance(r.get("amenity"), str):
            if r["amenity"] in ("bench", "waste_basket", "vending_machine", "parking_entrance", "bicycle_parking", "shelter"):
                continue
            kind = AMENITY_IT.get(r["amenity"], r["amenity"].replace("_", " "))
        elif isinstance(r.get("shop"), str):
            kind = "negozio"
        elif isinstance(r.get("leisure"), str):
            kind = LEISURE_IT.get(r["leisure"], r["leisure"].replace("_", " "))
        elif isinstance(r.get("place"), str):
            if r["place"] in ("city", "isolated_dwelling"):
                continue
            kind = PLACE_IT.get(r["place"], "luogo")
        elif isinstance(r.get("healthcare"), str):
            kind = "servizio sanitario"
        elif isinstance(r.get("building"), str):
            kind = "edificio"
        else:
            continue
        p = r.geometry.representative_point()
        name = r["name"]
        if kind == "stazione" and "stazione" not in name.lower():
            name = f"Stazione di {name}"
        # a bus stop name appears once (one entry per direction would only repeat it)
        key = (name.lower(), kind) if kind == "fermata del bus" else (name.lower(), round(p.x, 3), round(p.y, 3))
        if key in seen:
            continue
        seen.add(key)
        out.append([name, kind, int(round(p.x * 1e5)), int(round(p.y * 1e5)), 1])
    log.info("interfaccia: %d voci per la ricerca", len(out))
    return out


def build(cfg: dict[str, Any] | None = None, *, app: bool = True) -> dict[str, Any]:
    cfg = cfg or load_config()
    keys = param_keys(cfg)
    labels = param_labels(cfg)
    engine = Engine(cfg)
    ctx, static = engine.ctx, engine.static
    seg = gpd.read_parquet(PROCESSED / "segments.parquet").set_index("segment_id").loc[ctx.seg["segment_id"]].reset_index()
    n = ctx.n
    geoms, node_u, node_v, n_nodes = _orient(seg)

    # ---------------- static per-segment data
    x_luce, f_luce = static["luce"]
    x_vis, _ = static["visuale"]
    x_fuga, _ = static["vie_di_fuga"]
    x_perc, f_perc = static["percorso"]
    suolo_day, f_suolo = params.land_use(ctx, static["landuse_samples"], dark=False)
    suolo_night, _ = params.land_use(ctx, static["landuse_samples"], dark=True)
    via_names = sorted(seg["via"].fillna(cfg["network"]["unnamed_label"]).unique())
    quartieri = sorted(seg["quartiere"].astype(str).unique())
    classes = sorted(seg["classe"].astype(str).unique())
    sources = list(LIGHT_SOURCE_LABELS)
    static_bits = ((f_luce == scoring.PROXY).astype(np.uint8)
                   | ((f_perc == scoring.PROXY).astype(np.uint8) << 1)
                   | ((f_suolo == scoring.EXCLUDED).astype(np.uint8) << 2)
                   | ((static["blocking"] > 0).astype(np.uint8) << 3))
    static_data = {
        "via": _b64(seg["via"].fillna(cfg["network"]["unnamed_label"]).map({v: i for i, v in enumerate(via_names)}).to_numpy(np.uint16)),
        "quartiere": _b64(seg["quartiere"].astype(str).map({v: i for i, v in enumerate(quartieri)}).to_numpy(np.uint8)),
        "classe": _b64(seg["classe"].astype(str).map({v: i for i, v in enumerate(classes)}).to_numpy(np.uint8)),
        "lunghezza": _b64(np.round(seg["lunghezza_m"].to_numpy()).clip(0, 65535).astype(np.uint16)),
        "fonte_luce": _b64(pd.Series(static["fonte_luce"]).map({v: i for i, v in enumerate(sources)}).fillna(0).to_numpy(np.uint8)),
        "luce": _b64(_u8(x_luce)), "visuale": _b64(_u8(x_vis)), "vie_di_fuga": _b64(_u8(x_fuga)),
        "percorso": _b64(_u8(x_perc)), "suolo_giorno": _b64(_u8(suolo_day)), "suolo_notte": _b64(_u8(suolo_night)),
        "bits": _b64(static_bits),
    }

    # ---------------- hourly data for a weekday and a Saturday of the reference week
    ref = date.fromisoformat(cfg["standard"]["reference_date"])
    days = {"feriale": ref, "weekend": ref + timedelta(days=(5 - ref.weekday()) % 7)}
    jp = keys.index("persone")
    hourly: dict[str, list[np.ndarray]] = {k: [] for k in ("persone", "fronti_attivi", "punti_aiuto", "trasporto", "bits")}
    bands, sun = {}, {}
    for kind, d in days.items():
        sunrise, sunset = timebands.sun_times(d, cfg)
        sun[kind] = {"alba": sunrise.strftime("%H:%M"), "tramonto": sunset.strftime("%H:%M"), "data": d.isoformat()}
        bands[kind] = []
        for hour in range(24):
            when = datetime.combine(d, time(hour, 30), timebands._tz(cfg))
            band = timebands.band_at(when, cfg)
            bands[kind].append(band)
            res = params.band_parameters(ctx, band, when, static)
            X, F = res["X"], res["F"]
            X[:, jp] = np.minimum(1.0, X[:, jp] / engine.people_norm)
            for k in ("persone", "fronti_attivi", "punti_aiuto", "trasporto"):
                hourly[k].append(_u8(X[:, keys.index(k)]))
            bits = ((F[:, keys.index("fronti_attivi")] == scoring.PROXY).astype(np.uint8)
                    | ((F[:, keys.index("punti_aiuto")] == scoring.PROXY).astype(np.uint8) << 1)
                    | ((res["pen_parco_buio"] > 0).astype(np.uint8) << 2)
                    | ((F[:, keys.index("trasporto")] == scoring.PROXY).astype(np.uint8) << 3))
            hourly["bits"].append(bits)
        log.info("interfaccia: ore calcolate per %s (%s)", kind, d)
    hourly_data = {k: _b64(np.concatenate(v)) for k, v in hourly.items()}

    # ---------------- context layers
    boundary = osm.load_boundary().geometry.iloc[0]
    feats = osm.load_features()
    quartieri_gdf = gpd.read_parquet(PROCESSED / "quartieri.parquet")
    parks = pois.parks(feats, cfg)
    water = feats[(feats.get("natural") == "water") & feats.geom_type.isin(["Polygon", "MultiPolygon"])]
    water = water[water.intersects(boundary)].copy()
    water["geometry"] = water.geometry.intersection(boundary)
    parks = parks[parks.intersects(boundary)].copy()
    parks["geometry"] = parks.geometry.intersection(boundary)
    layers = {
        "confine": json.loads(gpd.GeoSeries([boundary], crs="EPSG:4326").to_json()),
        "quartieri": _polygons_geojson(quartieri_gdf, cfg, 15.0, ["quartiere"]),
        "parchi": _polygons_geojson(parks, cfg, 5.0, []),
        "acqua": _polygons_geojson(water, cfg, 5.0, []),
        "non_pedonali": _non_walkable_roads(cfg, boundary),
    }

    # ---------------- model settings (mirrors config.yaml)
    model = {
        "keys": keys, "labels": [labels[k] for k in keys],
        "bands": {b: {"label": cfg["timebands"]["bands"][b]["label"], "dark": bool(cfg["timebands"]["bands"][b].get("dark")),
                      "weights": [round(float(v), 4) for v in scoring.base_weights(b, cfg)]}
                  for b in cfg["timebands"]["order"]},
        "profiles": {p: {"label": v["label"], "multipliers": v.get("multipliers") or {},
                         "lambda_factor": v.get("lambda_factor", 1.0), "dark_factor": v.get("dark_factor", 1.0)}
                     for p, v in cfg["profiles"].items()},
        "lambda_base": cfg["scoring"]["lambda_base"],
        "classes": cfg["scoring"]["classes"],
        "penalties": {"blocking": cfg["scoring"]["penalties"]["blocking"], "park_dark": cfg["scoring"]["penalties"]["park_dark"],
                      "dark": cfg["scoring"]["penalties"]["dark"]},
        "reliability": cfg["scoring"]["reliability_factors"],
        "rain": {"persone": cfg["params"]["persone"]["rain_factor"], "visuale": cfg["params"]["visuale"]["rain_factor"]},
        "excluded": ["episodi", "cura", "folla"],
        "scale": SCALE, "na": NA,
        "unnamed_label": cfg["network"]["unnamed_label"],
        "time": {"boundaries": cfg["timebands"]["boundaries"], "calendar": cfg["calendar"],
                 "center": {"lat": cfg["area"]["center"]["lat"], "lon": cfg["area"]["center"]["lon"]}},
        "routing": cfg["routing"],
    }
    meta = json.loads(params.PARAMS_META.read_text(encoding="utf-8"))
    payload = {
        "n": n, "model": model, "static": static_data, "hourly": hourly_data, "bands": bands, "sun": sun,
        "geometry": _geometry(geoms, cfg), "names": {"via": via_names, "quartiere": quartieri, "classe": classes,
                                                    "fonte_luce": [LIGHT_SOURCE_LABELS[s] for s in sources]},
        "layers": layers, "segment_ids": None,
        "graph": {"nodes": n_nodes, "u": _b64(node_u.astype(np.uint16)), "v": _b64(node_v.astype(np.uint16))},
        "info": {"osm": json.loads(osm.META.read_text(encoding="utf-8")).get("osm_timestamp"),
                 "luce_modello": meta.get("luce_modello"), "residenti": meta.get("residents_source"),
                 "generato": datetime.now().strftime("%d/%m/%Y %H:%M")},
    }
    if app:
        payload["buildings"] = _buildings(feats, boundary, cfg)
        payload["search"] = _search_index(seg, feats, boundary, cfg)
    return payload


def _mascots() -> dict[str, dict[str, str]]:
    """Lumi's illustrations (f = girl, m = boy) as data URIs."""
    out: dict[str, dict[str, str]] = {"f": {}, "m": {}}
    for path in sorted(MASCOTS.glob("*.webp")):
        guide, pose = path.stem.split("_", 1)
        out[guide][pose] = "data:image/webp;base64," + base64.b64encode(path.read_bytes()).decode("ascii")
    return out


def render(page: str, payload: dict[str, Any], *, artifact: bool = False) -> str:
    template = (SRC / f"{page}.html").read_text(encoding="utf-8")
    data = dict(payload)
    if page == "enti":
        data.pop("buildings", None)
        data.pop("search", None)
    html = (template
            .replace("/*__CORE__*/", (SRC / "core.js").read_text(encoding="utf-8"))
            .replace("/*__LEAFLET_CSS__*/", (FRONTEND / "vendor" / "leaflet-1.9.4.css").read_text(encoding="utf-8"))
            .replace("/*__MAPLIBRE_CSS__*/", (FRONTEND / "vendor" / "maplibre-gl-4.7.1.css").read_text(encoding="utf-8"))
            .replace("/*__IMG__*/null", json.dumps(_mascots(), separators=(",", ":")))
            .replace("/*__DATA__*/null", json.dumps(data, separators=(",", ":"), ensure_ascii=False)))
    if artifact:  # the artifact host adds doctype, html, head and body itself
        start, end = html.index("<!--PAGE-START-->"), html.index("<!--PAGE-END-->")
        return html[start + len("<!--PAGE-START-->"):end]
    return html


def main() -> None:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Genera le interfacce (frontend/enti.html e frontend/lumi.html)")
    parser.add_argument("--artifact-dir", help="scrive anche le versioni senza <html>/<head>/<body> in questa cartella")
    args = parser.parse_args()
    setup_logging()
    payload = build()
    for page, out in PAGES.items():
        out.write_text(render(page, payload), encoding="utf-8")
        log.info("interfaccia %s scritta in %s (%.1f MB)", page, out, out.stat().st_size / 1e6)
        if args.artifact_dir:
            Path(args.artifact_dir, f"{page}.html").write_text(render(page, payload, artifact=True), encoding="utf-8")
    (FRONTEND / "index.html").write_text((SRC / "index.html").read_text(encoding="utf-8"), encoding="utf-8")


if __name__ == "__main__":
    main()
