"""Public sources other than OSM: SIT Vicenza, ISTAT, dati.veneto.it, GTFS,
municipal events, Punti Viola, lighting.

Every source is optional: when a download is not possible the attempt is
recorded in ``data/raw/sources_log.json`` (and then in DATA_SOURCES.md) and
the pipeline keeps going. Files supplied by hand in ``data/manual/`` are
always preferred, so the team can unblock a source without code changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd

from model.config import load_config, resolve
from pipeline.common import log, probe, record_source

GEO_SUFFIXES = {".shp", ".gpkg", ".geojson", ".json", ".csv", ".parquet"}


def probe_all(cfg: dict[str, Any] | None = None) -> dict[str, dict[str, str]]:
    """Check which public endpoints are reachable from this machine."""
    cfg = cfg or load_config()
    results = {}
    for name, url in cfg["sources"]["probe_urls"].items():
        ok, detail = probe(url)
        results[name] = {"url": url, "raggiungibile": ok, "dettaglio": detail}
        record_source(f"probe_{name}", url=url, status="raggiungibile" if ok else "non raggiungibile", detail=detail)
        log.info("fonte %-22s %s (%s)", name, "OK" if ok else "NON raggiungibile", detail)
    return results


def _manual_files(folder: Path, words: tuple[str, ...] = ()) -> list[Path]:
    if not folder.exists():
        return []
    files = [p for p in folder.rglob("*") if p.suffix.lower() in GEO_SUFFIXES]
    if words:
        files = [p for p in files if any(w in p.stem.lower() for w in words)]
    return sorted(files)


def _read_points(path: Path) -> gpd.GeoDataFrame:
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
        lat = next(c for c in df.columns if c.lower() in {"lat", "latitude", "latitudine", "y"})
        lon = next(c for c in df.columns if c.lower() in {"lon", "lng", "longitude", "longitudine", "x"})
        return gpd.GeoDataFrame(df, geometry=gpd.points_from_xy(df[lon], df[lat]), crs="EPSG:4326")
    if path.suffix.lower() == ".parquet":
        return gpd.read_parquet(path)
    gdf = gpd.read_file(path)
    return gdf.set_crs("EPSG:3003") if gdf.crs is None else gdf


# --------------------------------------------------------------------------- #
# Lighting: SIT / City Green Light points (manual)
# --------------------------------------------------------------------------- #
def load_lamps(cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame | None:
    """Public lighting points, if the SIT / City Green Light dataset is supplied."""
    cfg = cfg or load_config()
    folder = resolve(cfg["sources"]["manual_dirs"]["lamps"])
    files = _manual_files(folder) + _manual_files(resolve(cfg["sources"]["manual_dirs"]["sit"]), ("luce", "lamp", "illumin"))
    for path in files:
        try:
            lamps = _read_points(path).to_crs("EPSG:4326")
        except Exception as exc:  # noqa: BLE001
            log.warning("punti luce %s non leggibili: %s", path, exc)
            continue
        lamps = lamps[lamps.geom_type == "Point"]
        if len(lamps):
            record_source("punti_luce", status="ok", file=str(path), n=len(lamps))
            return lamps
    record_source("punti_luce", status="non disponibile",
                  detail="nessun dataset dei punti luce in data/manual/punti_luce (atteso dal referente SIT)")
    return None


# --------------------------------------------------------------------------- #
# ISTAT census sections with population (manual or download)
# --------------------------------------------------------------------------- #
def load_istat_population(cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame | None:
    """Census sections of the municipality with a ``popolazione`` column.

    Expects the ISTAT "basi territoriali" shapefile and the "variabili
    censuarie" CSV in data/manual/istat/ (joined on the section code).
    """
    cfg = cfg or load_config()
    folder = resolve(cfg["sources"]["manual_dirs"]["istat"])
    shapes = _manual_files(folder)
    shapes = [p for p in shapes if p.suffix.lower() in {".shp", ".gpkg", ".geojson"}]
    tables = [p for p in _manual_files(folder) if p.suffix.lower() == ".csv"]
    if not shapes:
        record_source("istat", status="non disponibile",
                      detail="sezioni di censimento non presenti in data/manual/istat (download bloccato)")
        return None
    sections = gpd.read_file(shapes[0])
    sections = sections.set_crs("EPSG:32632") if sections.crs is None else sections
    code = next((c for c in sections.columns if c.upper() in {"SEZ21_ID", "SEZ2011", "SEZ21", "SEZ"}), None)
    pro_com = next((c for c in sections.columns if c.upper() == "PRO_COM"), None)
    if pro_com is not None:
        sections = sections[sections[pro_com].astype(int) == int(cfg["area"]["istat_pro_com"])]
    pop_col = next((c for c in sections.columns if c.upper() in {"POP21", "P1", "POP_TOT", "POPOLAZIONE"}), None)
    if pop_col is None and tables and code:
        table = pd.read_csv(tables[0], sep=None, engine="python")
        tcode = next((c for c in table.columns if c.upper() in {"SEZ21_ID", "SEZ2011", "SEZ21", "SEZ"}), None)
        tpop = next((c for c in table.columns if c.upper() in {"POP21", "P1", "POP_TOT"}), None)
        if tcode and tpop:
            sections = sections.merge(table[[tcode, tpop]], left_on=code, right_on=tcode, how="left")
            pop_col = tpop
    if pop_col is None:
        record_source("istat", status="incompleto", detail="sezioni senza colonna di popolazione")
        return None
    sections = sections.rename(columns={pop_col: "popolazione"})
    record_source("istat", status="ok", file=str(shapes[0]), n=len(sections))
    return sections[["popolazione", "geometry"]]


# --------------------------------------------------------------------------- #
# Punti Viola (manual CSV only, respecting the terms of use of the public map)
# --------------------------------------------------------------------------- #
def load_punti_viola(cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame | None:
    cfg = cfg or load_config()
    path = resolve(cfg["sources"]["manual_dirs"]["punti_viola"])
    if not path.exists():
        record_source("punti_viola", status="non disponibile",
                      detail="data/manual/punti_viola.csv assente; la mappa DonneXStrada non è raggiungibile da qui")
        return None
    pts = _read_points(path).to_crs("EPSG:4326")
    pts = pts.assign(categoria="punto_viola", opening_hours=pts.get("opening_hours"))
    record_source("punti_viola", status="ok", file=str(path), n=len(pts))
    return pts[["categoria", "opening_hours", "geometry"]]
