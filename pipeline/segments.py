"""Pedestrian segments and neighbourhoods.

A *segment* is an edge of the undirected, simplified OSM walk network between
two intersections (u->v and v->u merged). Besides intersections, a segment is
split where the street name or the road class changes, so that every segment
belongs to exactly one street ("via").

Neighbourhoods follow the fallback chain of the brief: SIT boundaries (manual
files) > OSM (place polygons or admin_level 9/10, or Voronoi cells around OSM
place nodes) > ISTAT census sections (manual files) > hexagonal grid.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
import shapely
from shapely.geometry import Polygon
from shapely.ops import unary_union

from model.config import load_config, resolve
from pipeline import osm
from pipeline.common import PROCESSED, log, record_source

SEGMENTS = PROCESSED / "segments.parquet"
QUARTIERI = PROCESSED / "quartieri.parquet"

# Edge attributes copied onto segments (lists are joined with ";")
SEGMENT_TAGS = [t for t in osm.WAY_TAGS if t not in {"name", "highway", "oneway", "junction", "lanes", "maxspeed", "ref"}]


def _join(value: Any) -> Any:
    """osmnx stores merged attributes as lists: keep them as 'a;b' strings."""
    if isinstance(value, (list, tuple, set)):
        vals = sorted({str(v) for v in value if v is not None and v == v})
        return ";".join(vals) if vals else None
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return str(value)


_CLASS_RANK = ["trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "living_street",
               "service", "pedestrian", "track", "footway", "path", "cycleway", "bridleway", "steps", "corridor"]


def _main_class(value: Any) -> str:
    """Single road class for a segment (the most 'major' one if several)."""
    if isinstance(value, (list, tuple, set)):
        vals = [str(v).replace("_link", "") for v in value]
        ranked = sorted(vals, key=lambda v: _CLASS_RANK.index(v) if v in _CLASS_RANK else len(_CLASS_RANK))
        return ranked[0]
    return str(value).replace("_link", "")


def _main_name(value: Any) -> str | None:
    if isinstance(value, (list, tuple, set)):
        vals = [str(v) for v in value if v is not None and v == v]
        return sorted(vals)[0] if vals else None
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    return str(value)


def build_segments(cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame:
    """Simplify the walk graph and return one row per undirected segment."""
    cfg = cfg or load_config()
    G = osm.load_walk_graph(cfg)
    log.info("grafo pedonale: %d nodi, %d archi orientati (non semplificato)", len(G), G.number_of_edges())
    Gs = ox.simplify_graph(G, edge_attrs_differ=cfg["network"]["split_on_attribute_change"])
    street_count = ox.stats.count_streets_per_node(Gs)
    Gu = ox.convert.to_undirected(Gs)
    nodes, edges = ox.graph_to_gdfs(Gu, nodes=True, edges=True, fill_edge_geometry=True)
    edges = edges.reset_index()
    log.info("tratti (archi non orientati, semplificati): %d", len(edges))

    out = gpd.GeoDataFrame(
        {
            "u": edges["u"].astype("int64"),
            "v": edges["v"].astype("int64"),
            "key": edges["key"].astype("int64"),
        },
        geometry=edges.geometry.values,
        crs=edges.crs,
    )
    lo = np.minimum(out["u"], out["v"])
    hi = np.maximum(out["u"], out["v"])
    out.insert(0, "segment_id", [f"{a}-{b}-{k}" for a, b, k in zip(lo, hi, out["key"])])
    out["nome"] = [_main_name(v) for v in edges.get("name", pd.Series([None] * len(edges)))]
    out["classe"] = [_main_class(v) for v in edges["highway"]]
    out["osm_ids"] = [_join(v) for v in edges["osmid"]]
    for tag in SEGMENT_TAGS:
        col = edges[tag] if tag in edges.columns else pd.Series([None] * len(edges))
        out[f"tag_{tag.replace(':', '_')}"] = [_join(v) for v in col]
    out["street_count_u"] = out["u"].map(street_count).fillna(0).astype(int)
    out["street_count_v"] = out["v"].map(street_count).fillna(0).astype(int)
    out["vicolo_cieco"] = (out[["street_count_u", "street_count_v"]].min(axis=1) <= 1)

    metric = out.to_crs(cfg["area"]["crs_metric"])
    out["lunghezza_m"] = metric.length.round(2)
    out = out[out["lunghezza_m"] > 0].copy()
    if out["segment_id"].duplicated().any():  # parallel edges with equal keys cannot happen, but be safe
        out["segment_id"] = out["segment_id"] + "-" + out.groupby("segment_id").cumcount().astype(str)
    return out.reset_index(drop=True)


# --------------------------------------------------------------------------- #
# Neighbourhoods
# --------------------------------------------------------------------------- #
def _read_any(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    if gdf.crs is None:  # no .prj: SIT data are usually Gauss-Boaga (EPSG:3003)
        gdf = gdf.set_crs("EPSG:3003")
    return gdf


def _name_column(gdf: gpd.GeoDataFrame) -> str | None:
    for col in gdf.columns:
        if col.lower() in {"nome", "name", "quartiere", "denominaz", "denominazione", "nome_quart", "circoscriz"}:
            return col
    text_cols = [c for c in gdf.columns if c != "geometry" and gdf[c].dtype == object]
    return text_cols[0] if text_cols else None


def neighbourhoods_from_sit(cfg: dict[str, Any], boundary: Polygon) -> gpd.GeoDataFrame | None:
    folder = resolve(cfg["sources"]["manual_dirs"]["sit"])
    if not folder.exists():
        return None
    files = [p for p in folder.rglob("*") if p.suffix.lower() in {".shp", ".gpkg", ".geojson", ".json"}
             and any(w in p.stem.lower() for w in ("quart", "circoscr", "zone"))]
    for path in files:
        gdf = _read_any(path).to_crs("EPSG:4326")
        centroid = unary_union(gdf.geometry.values).centroid
        if not boundary.buffer(0.02).contains(centroid):
            log.warning("SIT %s: il centroide non cade su Vicenza, controlla il sistema di riferimento", path.name)
            continue
        col = _name_column(gdf)
        out = gpd.GeoDataFrame({"quartiere": gdf[col].astype(str) if col else [f"Q{i+1}" for i in range(len(gdf))]},
                               geometry=gdf.geometry.values, crs="EPSG:4326")
        out["fonte_quartiere"] = f"SIT ({path.name})"
        return out
    return None


def _split_zone_name(name: str) -> list[str]:
    return [p.strip() for p in str(name).replace(" - ", "-").split("-") if p.strip()]


def _official_zone_population(cfg: dict[str, Any]) -> dict[str, float]:
    """Residents per zone from the Comune (latest year), keyed by zone name."""
    from pipeline import sources_public

    table = sources_public.load_comune_table("residenti_quartieri_eta", cfg)
    if table is None or not {"MASCHI", "FEMMINE", "QUARTIERE", "ANNO"} <= set(table.columns):
        return {}
    last = table[table["ANNO"] == table["ANNO"].max()]
    aliases = cfg["neighbourhoods"].get("zone_aliases", {})
    return {aliases.get(q, q): float(m + f) for q, m, f in zip(last["QUARTIERE"], last["MASCHI"], last["FEMMINE"])}


def _assign_sections(sec: gpd.GeoDataFrame, seeds: gpd.GeoDataFrame, targets: dict[str, float],
                     iterations: int = 400) -> np.ndarray:
    """Assign census sections to zones of one circoscrizione.

    Nearest zone point, with additive weights tuned so that the population of
    each zone approaches the official one (capacity-constrained Voronoi on
    sections). Without official figures it is the plain nearest point.
    """
    names = list(dict.fromkeys(seeds["quartiere"]))
    pts = sec.geometry.representative_point()
    dist = np.column_stack([
        np.min(np.column_stack([pts.distance(g).to_numpy() for g in seeds.loc[seeds["quartiere"] == n, "geometry"]]), axis=1)
        for n in names])
    pop = sec["popolazione"].to_numpy(dtype=float)
    weights = np.zeros(len(names))
    tgt = np.array([targets.get(n, np.nan) for n in names])
    if len(names) > 1 and not np.isnan(tgt).any() and tgt.sum() > 0:
        tgt = tgt * pop.sum() / tgt.sum()
        step = 200.0
        for _ in range(iterations):
            choice = np.argmin(dist - weights, axis=1)
            got = np.bincount(choice, weights=pop, minlength=len(names))
            weights += step * (tgt - got) / np.maximum(tgt, 1.0)
            step *= 0.99
    choice = np.argmin(dist - weights, axis=1)
    return np.array(names)[choice]


def neighbourhoods_from_official_zones(cfg: dict[str, Any], boundary: Polygon, feats: gpd.GeoDataFrame) -> gpd.GeoDataFrame | None:
    """The 22 official zones of the Comune, rebuilt from ISTAT census sections.

    The Comune publishes the list of zones with their circoscrizione
    (dati.veneto.it) but not their boundaries (SIT not reachable). ISTAT gives
    the exact circoscrizione of every census section. Each section is assigned
    to the nearest zone point *within its own circoscrizione*, then sections are
    merged: circoscrizione boundaries are exact, zone boundaries follow
    section boundaries.
    """
    from pipeline import sources_public

    ncfg = cfg["neighbourhoods"]
    if not ncfg.get("official_zones", True):
        return None
    zones = sources_public.load_comune_table("zone_amministrative", cfg)
    sections = sources_public.load_istat_sections(cfg)
    if zones is None or sections is None or "circoscrizione" not in sections:
        return None
    metric = cfg["area"]["crs_metric"]
    places = feats[(feats.geom_type == "Point") & feats.get("place", pd.Series(index=feats.index, dtype=object)).notna()]
    places = places.to_crs(metric)
    place_pts = {str(n).lower(): g for n, g in zip(places["name"], places.geometry) if isinstance(n, str)}
    streets = gpd.read_parquet(SEGMENTS).to_crs(metric) if SEGMENTS.exists() else None
    seeds = []
    for row in zones.itertuples():
        name, circ = str(row.denominazione).strip(), int(row.circoscrizione)
        street = ncfg.get("zone_seed_streets", {}).get(name)
        parts = [street] if street else _split_zone_name(name)
        for part in parts:
            pt = place_pts.get(part.lower())
            if pt is None and streets is not None:
                same = streets[streets["nome"] == part]
                pt = same.union_all().centroid if len(same) else None
            if pt is None:
                hit = sources_public.geocode(f"{part}, Vicenza", cfg)
                pt = gpd.GeoSeries.from_xy([hit[1]], [hit[0]], crs="EPSG:4326").to_crs(metric).iloc[0] if hit else None
            if pt is not None:
                seeds.append({"quartiere": name, "circoscrizione": circ, "geometry": pt})
    if not seeds:
        return None
    seeds = gpd.GeoDataFrame(seeds, crs=metric)
    sec = sections.to_crs(metric).copy()
    targets = _official_zone_population(cfg)
    sec["quartiere"] = None
    for circ, idx in sec.groupby("circoscrizione").groups.items():
        cand = seeds[seeds["circoscrizione"] == circ]
        cand = cand if len(cand) else seeds
        sec.loc[idx, "quartiere"] = _assign_sections(sec.loc[idx], cand, targets)
    out = sec.dissolve(by="quartiere", aggfunc={"popolazione": "sum", "circoscrizione": "first"}, as_index=False)
    out = out.rename(columns={"popolazione": "popolazione_istat_2021"})
    out["geometry"] = out.geometry.intersection(gpd.GeoSeries([boundary], crs="EPSG:4326").to_crs(metric).iloc[0])
    out = out.to_crs("EPSG:4326")
    out["fonte_quartiere"] = ("22 zone del Comune (dati.veneto.it) ricostruite con le sezioni e le circoscrizioni "
                              "ISTAT 2021")
    return out[["quartiere", "circoscrizione", "popolazione_istat_2021", "fonte_quartiere", "geometry"]]


def neighbourhoods_from_osm(feats: gpd.GeoDataFrame, boundary: Polygon, cfg: dict[str, Any]) -> gpd.GeoDataFrame | None:
    ncfg = cfg["neighbourhoods"]
    metric = cfg["area"]["crs_metric"]
    polys = feats[feats.geom_type.isin(["Polygon", "MultiPolygon"])]
    is_place = polys.get("place", pd.Series(index=polys.index, dtype=object)).isin(ncfg["osm_place_values"])
    is_admin = (polys.get("boundary", pd.Series(index=polys.index, dtype=object)) == "administrative") & \
        polys.get("admin_level", pd.Series(index=polys.index, dtype=object)).astype(str).isin(ncfg["osm_admin_levels"])
    cand = polys[(is_place | is_admin) & polys.intersects(boundary)].copy()
    cand = cand[cand["name"].notna()] if "name" in cand else cand.iloc[0:0]
    if len(cand) >= 3:
        cand["geometry"] = cand.geometry.intersection(boundary)
        cover = cand.to_crs(metric).union_all().area / gpd.GeoSeries([boundary], crs="EPSG:4326").to_crs(metric).area.iloc[0]
        if cover >= 0.5:
            out = gpd.GeoDataFrame({"quartiere": cand["name"].astype(str).values}, geometry=cand.geometry.values, crs="EPSG:4326")
            out["fonte_quartiere"] = f"OSM poligoni (copertura {cover:.0%})"
            return out.dissolve(by="quartiere", as_index=False)

    points = feats[(feats.geom_type == "Point") & feats.get("place", pd.Series(index=feats.index, dtype=object)).isin(ncfg["osm_place_values"])]
    points = points[points.within(boundary) & points["name"].notna()]
    points = points.drop_duplicates("name")
    if len(points) >= 3:
        pts_m = points.to_crs(metric)
        boundary_m = gpd.GeoSeries([boundary], crs="EPSG:4326").to_crs(metric).iloc[0]
        cells = shapely.voronoi_polygons(shapely.MultiPoint(list(pts_m.geometry.values)), extend_to=boundary_m)
        cells = gpd.GeoDataFrame(geometry=list(cells.geoms), crs=metric)
        cells = cells.sjoin(pts_m[["name", "place", "geometry"]], predicate="contains", how="inner")
        cells["geometry"] = cells.geometry.intersection(boundary_m)
        out = gpd.GeoDataFrame({"quartiere": cells["name"].astype(str).values}, geometry=cells.geometry.values, crs=metric)
        out = out.to_crs("EPSG:4326")
        out["fonte_quartiere"] = f"OSM place (punti: {len(points)}), confini approssimati con celle di Voronoi"
        return out
    return None


def neighbourhoods_from_istat(cfg: dict[str, Any], boundary: Polygon) -> gpd.GeoDataFrame | None:
    folder = resolve(cfg["sources"]["manual_dirs"]["istat"])
    if not folder.exists():
        return None
    for path in folder.rglob("*.shp"):
        gdf = _read_any(path).to_crs("EPSG:4326")
        gdf = gdf[gdf.intersects(boundary)]
        col = next((c for c in gdf.columns if c.upper() in {"ACE", "SEZ21_ID", "SEZ2011", "SEZ"}), None)
        if col is None or gdf.empty:
            continue
        out = gpd.GeoDataFrame({"quartiere": ("ACE " if col.upper() == "ACE" else "Sezione ") + gdf[col].astype(str)},
                               geometry=gdf.geometry.values, crs="EPSG:4326")
        out = out.dissolve(by="quartiere", as_index=False)
        out["fonte_quartiere"] = f"ISTAT ({path.name})"
        return out
    return None


def hex_grid(boundary: Polygon, cfg: dict[str, Any]) -> gpd.GeoDataFrame:
    metric = cfg["area"]["crs_metric"]
    b = gpd.GeoSeries([boundary], crs="EPSG:4326").to_crs(metric).iloc[0]
    size = float(cfg["neighbourhoods"]["hex_size_m"])
    w, h = np.sqrt(3) * size, 2 * size
    minx, miny, maxx, maxy = b.bounds
    cells, row = [], 0
    y = miny - h
    while y < maxy + h:
        x = minx - w + (w / 2 if row % 2 else 0)
        while x < maxx + w:
            hexagon = Polygon([(x + size * np.cos(np.radians(a)), y + size * np.sin(np.radians(a))) for a in range(30, 390, 60)])
            if hexagon.intersects(b):
                cells.append(hexagon.intersection(b))
            x += w
        y += 0.75 * h
        row += 1
    out = gpd.GeoDataFrame({"quartiere": [f"Esagono {i + 1}" for i in range(len(cells))]}, geometry=cells, crs=metric)
    out = out.to_crs("EPSG:4326")
    out["fonte_quartiere"] = f"griglia esagonale ({size:.0f} m)"
    return out


def build_neighbourhoods(cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame:
    cfg = cfg or load_config()
    boundary = osm.load_boundary().geometry.iloc[0]
    feats = osm.load_features()
    for name, fn in (
        ("SIT", lambda: neighbourhoods_from_sit(cfg, boundary)),
        ("zone ufficiali + ISTAT", lambda: neighbourhoods_from_official_zones(cfg, boundary, feats)),
        ("OSM", lambda: neighbourhoods_from_osm(feats, boundary, cfg)),
        ("ISTAT", lambda: neighbourhoods_from_istat(cfg, boundary)),
    ):
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - a broken optional source must not stop the pipeline
            log.warning("quartieri da %s non utilizzabili: %s", name, exc)
            result = None
        if result is not None and len(result):
            log.info("quartieri: %d da %s", len(result), result["fonte_quartiere"].iloc[0])
            record_source("quartieri", status="ok", fonte=result["fonte_quartiere"].iloc[0], n=len(result))
            return result.reset_index(drop=True)
        log.info("quartieri: fonte %s non disponibile", name)
    result = hex_grid(boundary, cfg)
    record_source("quartieri", status="fallback", fonte=result["fonte_quartiere"].iloc[0], n=len(result))
    return result


def assign_neighbourhood(segments: gpd.GeoDataFrame, quartieri: gpd.GeoDataFrame, cfg: dict[str, Any]) -> pd.Series:
    """Neighbourhood containing the midpoint of each segment."""
    metric = cfg["area"]["crs_metric"]
    seg_m = segments.to_crs(metric)
    mid = gpd.GeoDataFrame({"i": np.arange(len(seg_m))}, geometry=seg_m.geometry.interpolate(0.5, normalized=True), crs=metric)
    q = quartieri.to_crs(metric)
    joined = gpd.sjoin(mid, q[["quartiere", "geometry"]], how="left", predicate="within").drop_duplicates("i")
    missing = joined["quartiere"].isna()
    if missing.any():  # midpoints just outside every polygon: nearest neighbourhood
        near = gpd.sjoin_nearest(mid[missing.values], q[["quartiere", "geometry"]], how="left").drop_duplicates("i")
        joined.loc[missing, "quartiere"] = near.set_index("i").loc[joined.loc[missing, "i"], "quartiere"].values
    return pd.Series(joined.sort_values("i")["quartiere"].values, index=segments.index)


def run(cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame:
    cfg = cfg or load_config()
    segments = build_segments(cfg)
    quartieri = build_neighbourhoods(cfg)
    segments["quartiere"] = assign_neighbourhood(segments, quartieri, cfg)
    unnamed = cfg["network"]["unnamed_label"]
    segments["via"] = segments["nome"].fillna(unnamed)
    segments["via_id"] = np.where(
        segments["nome"].notna(),
        segments["quartiere"].astype(str) + "|" + segments["nome"].fillna(""),
        "tratto|" + segments["segment_id"],
    )
    cols = ["segment_id", "nome", "via", "via_id", "classe", "lunghezza_m", "quartiere", "u", "v", "key",
            "street_count_u", "street_count_v", "vicolo_cieco", "osm_ids"] + \
        [c for c in segments.columns if c.startswith("tag_")] + ["geometry"]
    segments = segments[cols].to_crs("EPSG:4326")
    PROCESSED.mkdir(parents=True, exist_ok=True)
    segments.to_parquet(SEGMENTS, index=False)
    quartieri.to_parquet(QUARTIERI, index=False)
    log.info("salvati %d tratti in %s", len(segments), SEGMENTS)
    return segments


def load_segments() -> gpd.GeoDataFrame:
    return gpd.read_parquet(SEGMENTS)


def load_quartieri() -> gpd.GeoDataFrame:
    return gpd.read_parquet(QUARTIERI)
