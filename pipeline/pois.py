"""Points of interest, opening hours and other OSM layers used by the parameters."""

from __future__ import annotations

from datetime import datetime
from functools import lru_cache
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from model.config import load_config

try:  # opening-hours-py (Rust implementation of the OSM opening_hours spec)
    from opening_hours import OpeningHours
except ImportError:  # pragma: no cover - the pipeline falls back to category defaults
    OpeningHours = None


# --------------------------------------------------------------------------- #
# opening_hours
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=20000)
def _parse(expr: str):
    if OpeningHours is None:
        return None
    try:
        return OpeningHours(expr)
    except Exception:  # noqa: BLE001 - malformed tags are common in OSM
        return None


def is_open(expr: str | None, when: datetime) -> bool | None:
    """True/False if ``expr`` can be evaluated at ``when``; None if unparsable."""
    if not expr or not isinstance(expr, str):
        return None
    oh = _parse(expr.strip())
    if oh is None:
        return None
    try:
        return bool(oh.is_open(when.replace(tzinfo=None)))
    except Exception:  # noqa: BLE001
        return None


def category(row: pd.Series) -> str:
    """POI category used for default opening hours."""
    amenity = row.get("amenity")
    if isinstance(amenity, str) and amenity:
        return amenity
    if isinstance(row.get("shop"), str):
        return "shop"
    if isinstance(row.get("leisure"), str):
        return row["leisure"]
    return "other"


def open_status(pois: pd.DataFrame, when: datetime, cfg: dict[str, Any] | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Open/closed for each POI at ``when`` and whether the answer is measured.

    Explicit ``opening_hours`` -> measured; otherwise the category default
    from ``config.yaml -> pois.default_hours`` -> proxy (open=False if no
    default exists).
    """
    cfg = cfg or load_config()
    defaults = cfg["pois"]["default_hours"]
    is_open_arr = np.zeros(len(pois), dtype=bool)
    measured = np.zeros(len(pois), dtype=bool)
    hours = pois["opening_hours"] if "opening_hours" in pois else pd.Series([None] * len(pois), index=pois.index)
    cats = pois["categoria"] if "categoria" in pois else pois.apply(category, axis=1)
    for i, (expr, cat) in enumerate(zip(hours, cats)):
        state = is_open(expr, when)
        if state is not None:
            is_open_arr[i] = state
            measured[i] = True
            continue
        default = defaults.get(cat)
        state = is_open(default, when) if default else None
        is_open_arr[i] = bool(state)
    return is_open_arr, measured


# --------------------------------------------------------------------------- #
# Layers extracted from the OSM features table
# --------------------------------------------------------------------------- #
def _col(df: pd.DataFrame, name: str) -> pd.Series:
    return df[name] if name in df else pd.Series([None] * len(df), index=df.index, dtype=object)


def as_points(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Polygons -> representative points (shops mapped as building outlines)."""
    out = gdf.copy()
    poly = out.geom_type.isin(["Polygon", "MultiPolygon"])
    out.loc[poly, "geometry"] = out.loc[poly, "geometry"].representative_point()
    return out[out.geom_type == "Point"]


def activities(feats: gpd.GeoDataFrame, cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame:
    """Shops and the amenities listed in the brief, as points, with category."""
    cfg = cfg or load_config()
    mask = _col(feats, "shop").notna() | _col(feats, "amenity").isin(cfg["pois"]["amenities"])
    pois = as_points(feats[mask])
    pois = pois.drop_duplicates(subset=["element", "osmid"])
    pois = pois.assign(categoria=pois.apply(category, axis=1))
    return pois.reset_index(drop=True)


def help_points(feats: gpd.GeoDataFrame, cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame:
    """Help points: pharmacies, bars, police, hospitals (plus Punti Viola if supplied).

    Shelters and support facilities for women are deliberately never used.
    """
    cfg = cfg or load_config()
    amen = cfg["params"]["punti_aiuto"]["amenities"]
    pts = as_points(feats[_col(feats, "amenity").isin(amen)])
    pts = pts[_col(pts, "social_facility").isna()]
    pts = pts.drop_duplicates(subset=["element", "osmid"])
    return pts.assign(categoria=pts["amenity"]).reset_index(drop=True)


def transit_stops(feats: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Bus stops, platforms and railway stations, with mode and comfort flags."""
    hw = _col(feats, "highway")
    pt = _col(feats, "public_transport")
    rw = _col(feats, "railway")
    is_train = rw.isin(["station", "halt"]) | (pt.eq("station") & _col(feats, "train").eq("yes"))
    is_bus = hw.eq("bus_stop") | (pt.eq("platform") & ~_col(feats, "railway").eq("platform"))
    stops = as_points(feats[is_bus | is_train]).copy()
    stops["modo"] = np.where(is_train.loc[stops.index], "train", "bus")
    stops["comfort"] = _col(stops, "shelter").eq("yes") | _col(stops, "lit").eq("yes") | stops["modo"].eq("train")
    return stops.drop_duplicates(subset=["element", "osmid"]).reset_index(drop=True)


def street_lamps(feats: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    lamps = feats[_col(feats, "highway").eq("street_lamp") & (feats.geom_type == "Point")]
    return lamps.reset_index(drop=True)


def benches(feats: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    return as_points(feats[_col(feats, "amenity").eq("bench") | _col(feats, "leisure").eq("picnic_table")]).reset_index(drop=True)


def barrier_lines(feats: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    b = feats[_col(feats, "barrier").isin(["wall", "hedge", "fence", "retaining_wall", "city_wall"])]
    return b[b.geom_type.isin(["LineString", "MultiLineString"])].reset_index(drop=True)


def rail_lines(feats: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    r = feats[_col(feats, "railway").isin(["rail", "light_rail", "tram", "narrow_gauge"])]
    return r[r.geom_type.isin(["LineString", "MultiLineString"])].reset_index(drop=True)


def parks(feats: gpd.GeoDataFrame, cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame:
    cfg = cfg or load_config()
    kinds = cfg["params"]["penalita"]["parks"]
    p = feats[_col(feats, "leisure").isin(kinds) & feats.geom_type.isin(["Polygon", "MultiPolygon"])]
    return p.reset_index(drop=True)


def residential_buildings(feats: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Buildings that can host residents (used when ISTAT data are missing)."""
    b = _col(feats, "building")
    residential = b.isin(["residential", "apartments", "house", "detached", "semidetached_house", "terrace",
                          "yes", "dormitory", "farm"])
    other_use = _col(feats, "amenity").notna() | _col(feats, "shop").notna() | _col(feats, "leisure").notna()
    out = feats[residential & ~other_use & feats.geom_type.isin(["Polygon", "MultiPolygon"])]
    return out.reset_index(drop=True)


LANDUSE_FROM_LEISURE = {"park": "park", "garden": "park", "playground": "park", "dog_park": "park",
                        "pitch": "sport", "sports_centre": "sport", "stadium": "sport", "track": "sport",
                        "fitness_station": "sport", "golf_course": "sport"}
LANDUSE_FROM_AMENITY = {"parking": "parking", "school": "education", "university": "education",
                        "college": "education", "kindergarten": "education", "hospital": "institutional",
                        "grave_yard": "cemetery", "place_of_worship": "religious", "townhall": "civic"}
LANDUSE_ALIASES = {"village_green": "grass", "recreation_ground": "park", "greenhouse_horticulture": "farmland",
                   "plant_nursery": "farmland", "garages": "depot", "religious": "religious",
                   "railway": "railway", "retail": "retail", "allotments": "allotments", "flowerbed": "grass"}


def landuse_polygons(feats: gpd.GeoDataFrame, cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame:
    """Polygons classified into the land-use classes of config (priority order)."""
    cfg = cfg or load_config()
    ucfg = cfg["params"]["uso_suolo"]
    known = set(ucfg["values"])
    poly = feats[feats.geom_type.isin(["Polygon", "MultiPolygon"])]
    cls = pd.Series(None, index=poly.index, dtype=object)
    lu = _col(poly, "landuse").map(lambda v: LANDUSE_ALIASES.get(v, v) if isinstance(v, str) else None)
    cls = cls.fillna(lu.where(lu.isin(known)))
    cls = cls.fillna(_col(poly, "natural").map({"wood": "wood", "scrub": "scrub", "grassland": "meadow", "heath": "scrub"}))
    leisure = _col(poly, "leisure").map(LANDUSE_FROM_LEISURE)
    amenity = _col(poly, "amenity").map(LANDUSE_FROM_AMENITY)
    # leisure/amenity polygons are more specific than the landuse they sit in
    cls = leisure.fillna(amenity).fillna(cls)
    out = poly.assign(classe_suolo=cls)
    out = out[out["classe_suolo"].isin(known)].copy()
    priority = {k: i for i, k in enumerate(ucfg["priority"])}
    out["priorita"] = out["classe_suolo"].map(priority).fillna(len(priority)).astype(int)
    return out[["classe_suolo", "priorita", "geometry"]].reset_index(drop=True)
