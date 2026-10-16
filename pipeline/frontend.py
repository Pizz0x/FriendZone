"""Build the beta interface: one self-contained HTML page (frontend/index.html).

The page recomputes S in the browser for any hour, day type, sex, age group
and weather, from parameters precomputed here for every hour of a weekday and
of a Saturday of the reference week. Data are packed as gzip + base64 typed
arrays and decoded with the browser's DecompressionStream.

    python -m pipeline.frontend            # writes frontend/index.html
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
TEMPLATE = FRONTEND / "template.html"
OUTPUT = FRONTEND / "index.html"
SCALE = 250.0          # parameter values are stored as round(x * 250); 255 = not available
NA = 255


def _b64(arr: np.ndarray) -> str:
    return base64.b64encode(gzip.compress(np.ascontiguousarray(arr).tobytes(), 9)).decode("ascii")


def _u8(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    out = np.where(np.isnan(x), NA, np.round(np.clip(x, 0, 1) * SCALE))
    return out.astype(np.uint8)


def _geometry(segments: gpd.GeoDataFrame, cfg: dict[str, Any]) -> dict[str, str]:
    """Line vertices quantised to 1e-5 degrees, delta-encoded per segment."""
    metric = cfg["area"]["crs_metric"]
    geoms = segments.to_crs(metric).geometry.simplify(1.0).to_crs("EPSG:4326")
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


def build(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    keys = param_keys(cfg)
    labels = param_labels(cfg)
    engine = Engine(cfg)
    ctx, static = engine.ctx, engine.static
    seg = gpd.read_parquet(PROCESSED / "segments.parquet").set_index("segment_id").loc[ctx.seg["segment_id"]].reset_index()
    n = ctx.n

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
    }
    meta = json.loads(params.PARAMS_META.read_text(encoding="utf-8"))
    payload = {
        "n": n, "model": model, "static": static_data, "hourly": hourly_data, "bands": bands, "sun": sun,
        "geometry": _geometry(seg, cfg), "names": {"via": via_names, "quartiere": quartieri, "classe": classes,
                                                    "fonte_luce": [LIGHT_SOURCE_LABELS[s] for s in sources]},
        "layers": layers, "segment_ids": None,
        "info": {"osm": json.loads(osm.META.read_text(encoding="utf-8")).get("osm_timestamp"),
                 "luce_modello": meta.get("luce_modello"), "residenti": meta.get("residents_source"),
                 "generato": datetime.now().strftime("%d/%m/%Y %H:%M")},
    }
    return payload


def render(payload: dict[str, Any], *, artifact: bool = False) -> str:
    template = TEMPLATE.read_text(encoding="utf-8")
    css = (FRONTEND / "vendor" / "leaflet-1.9.4.css").read_text(encoding="utf-8")
    html = template.replace("/*__LEAFLET_CSS__*/", css).replace("/*__DATA__*/null", json.dumps(payload, separators=(",", ":"), ensure_ascii=False))
    if artifact:  # the artifact host adds doctype, html, head and body itself
        start, end = html.index("<!--PAGE-START-->"), html.index("<!--PAGE-END-->")
        return html[start + len("<!--PAGE-START-->"):end]
    return html


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Genera l'interfaccia beta (frontend/index.html)")
    parser.add_argument("--artifact", help="scrive anche la versione senza <html>/<head>/<body> in questo percorso")
    args = parser.parse_args()
    setup_logging()
    payload = build()
    OUTPUT.write_text(render(payload), encoding="utf-8")
    log.info("interfaccia scritta in %s (%.1f MB)", OUTPUT, OUTPUT.stat().st_size / 1e6)
    if args.artifact:
        from pathlib import Path

        Path(args.artifact).write_text(render(payload, artifact=True), encoding="utf-8")


if __name__ == "__main__":
    main()
