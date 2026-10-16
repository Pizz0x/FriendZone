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
ISTAT_CACHE = Path("data/raw/istat/sezioni_vicenza.parquet")


def download_istat_sections(cfg: dict[str, Any]) -> gpd.GeoDataFrame:
    """Census sections 2021 of the municipality from the ISTAT "basi territoriali".

    The regional archive includes, for every section, the 2021 population
    (POP21) and the sub-municipal area code (COM_ASC1 = circoscrizione).
    """
    import zipfile

    from pipeline.common import http_get

    icfg = cfg["sources"]["istat"]
    raw_dir = resolve(Path("data/raw/istat"))
    raw_dir.mkdir(parents=True, exist_ok=True)
    zip_path = raw_dir / Path(icfg["basi_territoriali_url"]).name
    if not zip_path.exists():
        zip_path.write_bytes(http_get(icfg["basi_territoriali_url"], timeout=600))
    with zipfile.ZipFile(zip_path) as zf:
        shp = next(n for n in zf.namelist() if n.lower().endswith(".shp"))
        extract_dir = raw_dir / "shp"
        zf.extractall(extract_dir, members=[n for n in zf.namelist() if Path(n).stem == Path(shp).stem])
    sections = gpd.read_file(extract_dir / shp, where=f"PRO_COM={int(cfg['area']['istat_pro_com'])}")
    keep = ["SEZ21_ID", "COM_ASC1", "POP21", "FAM21", "EDI21", "geometry"]
    return sections[[c for c in keep if c in sections.columns]]


def load_istat_sections(cfg: dict[str, Any] | None = None, *, force: bool = False) -> gpd.GeoDataFrame | None:
    """ISTAT sections with ``popolazione`` and ``circoscrizione`` (EPSG:32632).

    Order: files supplied by hand in data/manual/istat/, then the ISTAT
    download (cached). None if neither is available.
    """
    cfg = cfg or load_config()
    manual = load_istat_population_manual(cfg)
    if manual is not None:
        return manual
    cache = resolve(ISTAT_CACHE)
    try:
        if cache.exists() and not force:
            sections = gpd.read_parquet(cache)
        else:
            sections = download_istat_sections(cfg)
            cache.parent.mkdir(parents=True, exist_ok=True)
            sections.to_parquet(cache, index=False)
    except Exception as exc:  # noqa: BLE001 - optional source
        record_source("istat", status="non disponibile", detail=f"{type(exc).__name__}: {exc}"[:200])
        return None
    out = sections.rename(columns={"POP21": "popolazione", "SEZ21_ID": "sezione"})
    if "COM_ASC1" in out:
        out["circoscrizione"] = out["COM_ASC1"].astype(int) % 1000
    record_source("istat", status="ok", url=cfg["sources"]["istat"]["basi_territoriali_url"], sezioni=len(out),
                  popolazione_2021=int(out["popolazione"].sum()))
    return out


def load_istat_population(cfg: dict[str, Any] | None = None) -> gpd.GeoDataFrame | None:
    """Census sections with a ``popolazione`` column (manual files or ISTAT download)."""
    sections = load_istat_sections(cfg)
    return None if sections is None else sections[["popolazione", "geometry"]]


def load_istat_population_manual(cfg: dict[str, Any]) -> gpd.GeoDataFrame | None:
    """Sections supplied by hand in data/manual/istat/ (shapefile + optional CSV)."""
    folder = resolve(cfg["sources"]["manual_dirs"]["istat"])
    shapes = [p for p in _manual_files(folder) if p.suffix.lower() in {".shp", ".gpkg", ".geojson"}]
    tables = [p for p in _manual_files(folder) if p.suffix.lower() == ".csv"]
    if not shapes:
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
        return None
    sections = sections.rename(columns={pop_col: "popolazione"})
    record_source("istat", status="ok (file manuale)", file=str(shapes[0]), n=len(sections))
    return sections


# --------------------------------------------------------------------------- #
# Comune di Vicenza open data (dati.veneto.it, CKAN datastore dumps)
# --------------------------------------------------------------------------- #
def load_comune_table(name: str, cfg: dict[str, Any] | None = None) -> pd.DataFrame | None:
    """A table published by the Comune di Vicenza on dati.veneto.it (cached CSV)."""
    from pipeline.common import http_get

    cfg = cfg or load_config()
    ccfg = cfg["sources"]["comune_vicenza"]
    resource = ccfg["tables"][name]
    cache = resolve(Path("data/raw/comune")) / f"{name}.csv"
    try:
        if not cache.exists():
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_bytes(http_get(ccfg["datastore_dump_url"].format(resource=resource), timeout=180))
        df = pd.read_csv(cache, sep=";")
    except Exception as exc:  # noqa: BLE001 - optional source
        record_source(f"comune_{name}", status="non disponibile", detail=f"{type(exc).__name__}: {exc}"[:200])
        return None
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    record_source(f"comune_{name}", status="ok", righe=len(df), risorsa=resource)
    return df


# --------------------------------------------------------------------------- #
# Geocoding (Nominatim: 1 request per second, dedicated user agent, cache)
# --------------------------------------------------------------------------- #
def geocode(query: str, cfg: dict[str, Any] | None = None) -> tuple[float, float] | None:
    """(lat, lon) of a place in the study area, cached on disk."""
    import json
    import time

    import requests

    cfg = cfg or load_config()
    cache = resolve(Path("data/raw/geocode.json"))
    data = json.loads(cache.read_text(encoding="utf-8")) if cache.exists() else {}
    if query in data:
        return tuple(data[query]) if data[query] else None
    west, south, east, north = cfg["area"]["extract_bbox"]
    time.sleep(1.1)
    try:
        resp = requests.get("https://nominatim.openstreetmap.org/search",
                            params={"q": query, "format": "json", "limit": 1, "viewbox": f"{west},{north},{east},{south}",
                                    "bounded": 1}, headers={"User-Agent": cfg["sources"]["user_agent"]}, timeout=30)
        resp.raise_for_status()
        hits = resp.json()
    except Exception as exc:  # noqa: BLE001
        log.warning("geocodifica di %s non riuscita: %s", query, exc)
        return None
    result = [float(hits[0]["lat"]), float(hits[0]["lon"])] if hits else None
    data[query] = result
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    return tuple(result) if result else None


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


# --------------------------------------------------------------------------- #
# Population grid: Meta / CIESIN High Resolution Settlement Layer (AWS S3)
# --------------------------------------------------------------------------- #
HRSL_CACHE = Path("data/raw/hrsl/hrsl_vicenza.parquet")


def load_population_grid(cfg: dict[str, Any] | None = None, *, force: bool = False) -> gpd.GeoDataFrame | None:
    """Population per ~30 m pixel (total, women, 60+) around the municipality.

    Source: Data for Good at Meta & CIESIN, High Resolution Settlement Layer,
    cloud-optimised GeoTIFFs on the AWS Open Data registry (CC BY 4.0). Used
    instead of ISTAT census sections when those are not available.
    """
    cfg = cfg or load_config()
    hcfg = cfg["sources"]["hrsl"]
    cache = resolve(HRSL_CACHE)
    if cache.exists() and not force:
        return gpd.read_parquet(cache)
    try:
        import numpy as np
        import rasterio
        from rasterio.windows import from_bounds

        from pipeline import osm

        west, south, east, north = osm.load_boundary().to_crs("EPSG:4326").total_bounds
        m = float(hcfg["margin_deg"])
        layers = {}
        env = {"GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR", "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".vrt,.tif"}
        with rasterio.Env(**env):
            for name, layer in hcfg["layers"].items():
                url = f"/vsicurl/{hcfg['base_url']}/hrsl_{layer}/hrsl_{layer}-latest.vrt"
                with rasterio.open(url) as src:
                    win = from_bounds(west - m, south - m, east + m, north + m, src.transform).round_offsets().round_lengths()
                    arr = src.read(1, window=win)
                    transform = src.window_transform(win)
                layers[name] = np.nan_to_num(arr, nan=0.0)
        rows, cols = np.nonzero(layers["popolazione"] > 0)
        xs, ys = rasterio.transform.xy(transform, rows, cols)
        grid = gpd.GeoDataFrame({k: v[rows, cols].astype("float32") for k, v in layers.items()},
                                geometry=gpd.points_from_xy(xs, ys), crs="EPSG:4326")
    except Exception as exc:  # noqa: BLE001 - optional source
        record_source("hrsl", status="non disponibile", detail=f"{type(exc).__name__}: {exc}"[:200])
        log.warning("popolazione HRSL non disponibile: %s", exc)
        return None
    cache.parent.mkdir(parents=True, exist_ok=True)
    grid.to_parquet(cache, index=False)
    record_source("hrsl", status="ok", url=hcfg["base_url"], pixels=len(grid),
                  popolazione_finestra=round(float(grid["popolazione"].sum())))
    return grid


# --------------------------------------------------------------------------- #
# Overture Maps places (AWS S3): shops and venues missing from OSM
# --------------------------------------------------------------------------- #
OVERTURE_CACHE = Path("data/raw/overture/places.parquet")


def _overture_filesystem():
    import os

    import pyarrow.fs as pafs

    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    return pafs.S3FileSystem(anonymous=True, region="us-west-2", proxy_options=proxy or None)


def download_overture_places(cfg: dict[str, Any]) -> gpd.GeoDataFrame:
    """Read only the row groups of the places theme that overlap the study area."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.fs as pafs
    import pyarrow.parquet as pq
    import shapely

    ocfg = cfg["sources"]["overture"]
    west, south, east, north = cfg["area"]["extract_bbox"]
    fs = _overture_filesystem()
    base = f"{ocfg['bucket']}/release/{ocfg['release']}/theme=places/type=place/"
    files = [f.path for f in fs.get_file_info(pafs.FileSelector(base)) if f.path.endswith(".parquet")]
    tables = []
    for path in files:
        pf = pq.ParquetFile(path, filesystem=fs)
        md = pf.metadata
        idx = {md.schema.column(i).path: i for i in range(md.num_columns) if md.schema.column(i).path.startswith("bbox.")}
        groups = []
        for r in range(md.num_row_groups):
            st = {k: md.row_group(r).column(i).statistics for k, i in idx.items()}
            if all(s is not None and s.has_min_max for s in st.values()) and st["bbox.xmax"].min <= east and \
                    st["bbox.xmin"].max >= west and st["bbox.ymax"].min <= north and st["bbox.ymin"].max >= south:
                groups.append(r)
        if groups:
            t = pf.read_row_groups(groups, columns=["id", "geometry", "confidence", "operating_status",
                                                    "basic_category", "names", "sources"])
            bbox = pf.read_row_groups(groups, columns=["bbox"]).column("bbox").combine_chunks()
            x, y = pc.struct_field(bbox, "xmin"), pc.struct_field(bbox, "ymin")
            mask = pc.and_(pc.and_(pc.greater_equal(x, west), pc.less_equal(x, east)),
                           pc.and_(pc.greater_equal(y, south), pc.less_equal(y, north)))
            tables.append(t.filter(mask))
    table = pa.concat_tables(tables) if tables else None
    if table is None or table.num_rows == 0:
        raise RuntimeError("nessun luogo Overture nel riquadro")
    df = table.to_pandas()
    df["nome"] = df.pop("names").map(lambda n: n.get("primary") if isinstance(n, dict) else None)
    df["dataset"] = df.pop("sources").map(
        lambda s: ",".join(sorted({x["dataset"] for x in s} - {"Overture"})) if s is not None else "")
    df["geometry"] = shapely.from_wkb(df["geometry"])
    return gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")


def load_overture_places(cfg: dict[str, Any] | None = None, *, force: bool = False) -> gpd.GeoDataFrame | None:
    """Overture places mapped to the POI categories of the model (opening hours unknown)."""
    cfg = cfg or load_config()
    ocfg = cfg["sources"]["overture"]
    if not ocfg.get("enabled", True):
        return None
    cache = resolve(OVERTURE_CACHE)
    try:
        if cache.exists() and not force:
            raw = gpd.read_parquet(cache)
        else:
            raw = download_overture_places(cfg)
            cache.parent.mkdir(parents=True, exist_ok=True)
            raw.to_parquet(cache, index=False)
    except Exception as exc:  # noqa: BLE001 - optional source
        record_source("overture_places", status="non disponibile", detail=f"{type(exc).__name__}: {exc}"[:200])
        log.warning("luoghi Overture non disponibili: %s", exc)
        return None
    mapping = ocfg["category_map"]
    trusted = set(ocfg["trusted_datasets"])
    ok_source = raw["dataset"].map(lambda d: bool(trusted & set(d.split(","))) if isinstance(d, str) else False) | \
        (raw["confidence"] >= ocfg["min_confidence_other"])
    keep = raw["basic_category"].isin(mapping) & raw["operating_status"].ne("permanently_closed") & ok_source & \
        (raw["confidence"] >= ocfg["min_confidence"])
    places = raw[keep].copy()
    places["categoria"] = places["basic_category"].map(mapping)
    places["shop"] = places["categoria"].where(places["categoria"].eq("shop"))
    places["amenity"] = places["categoria"].where(places["categoria"].ne("shop"))
    places["opening_hours"] = None
    places["fonte"] = "overture"
    record_source("overture_places", status="ok", release=ocfg["release"], luoghi_nel_riquadro=len(raw),
                  usati=len(places), licenza="CDLA-Permissive-2.0")
    return places[["id", "nome", "categoria", "shop", "amenity", "opening_hours", "confidence", "dataset", "fonte",
                   "geometry"]].reset_index(drop=True)
