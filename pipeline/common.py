"""Shared helpers: paths, logging, HTTP with disk cache, GeoParquet I/O."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
import requests

from model.config import ROOT, load_config

RAW = ROOT / "data" / "raw"
MANUAL = ROOT / "data" / "manual"
PROCESSED = ROOT / "data" / "processed"
EXPORTS = ROOT / "exports"
REPORTS = ROOT / "reports"
SOURCE_LOG = RAW / "sources_log.json"

log = logging.getLogger("quartieri_vivi")


def setup_logging(level: int = logging.INFO) -> None:
    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")


def ensure_dirs() -> None:
    for d in (RAW, MANUAL, PROCESSED, EXPORTS, REPORTS):
        d.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


# --------------------------------------------------------------------------- #
# Source log: every download attempt is recorded for DATA_SOURCES.md
# --------------------------------------------------------------------------- #
def record_source(name: str, **info: Any) -> None:
    """Record the outcome of a data source attempt in data/raw/sources_log.json."""
    RAW.mkdir(parents=True, exist_ok=True)
    data = json.loads(SOURCE_LOG.read_text(encoding="utf-8")) if SOURCE_LOG.exists() else {}
    entry = data.get(name, {})
    entry.update(info)
    entry["updated_at"] = now_iso()
    data[name] = entry
    SOURCE_LOG.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def read_source_log() -> dict[str, Any]:
    return json.loads(SOURCE_LOG.read_text(encoding="utf-8")) if SOURCE_LOG.exists() else {}


# --------------------------------------------------------------------------- #
# HTTP with polite defaults and a disk cache
# --------------------------------------------------------------------------- #
_last_request: dict[str, float] = {}


def http_get(url: str, *, params: dict | None = None, cache_dir: Path | None = None, max_age_s: float | None = None,
             timeout: float | None = None, headers: dict | None = None) -> bytes:
    """GET with user agent, per-host throttling and an optional disk cache."""
    cfg = load_config()
    src = cfg["sources"]
    key = hashlib.sha256((url + json.dumps(params or {}, sort_keys=True)).encode()).hexdigest()[:24]
    cache_file = cache_dir / f"{key}.bin" if cache_dir else None
    if cache_file and cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if max_age_s is None or age < max_age_s:
            return cache_file.read_bytes()
    host = requests.utils.urlparse(url).netloc
    wait = float(src["request_delay_s"]) - (time.time() - _last_request.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    resp = requests.get(url, params=params, timeout=timeout or float(src["http_timeout_s"]),
                        headers={"User-Agent": src["user_agent"], **(headers or {})})
    _last_request[host] = time.time()
    resp.raise_for_status()
    if cache_file:
        cache_file.parent.mkdir(parents=True, exist_ok=True)
        cache_file.write_bytes(resp.content)
    return resp.content


def probe(url: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Check whether a URL is reachable. Returns (ok, detail)."""
    cfg = load_config()
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": cfg["sources"]["user_agent"]}, stream=True)
        resp.close()
        return resp.status_code < 400, f"HTTP {resp.status_code}"
    except requests.RequestException as exc:  # proxy denials surface here
        text = str(exc)
        if "403" in text and "Tunnel" in text:
            return False, "connessione rifiutata dalla policy di rete (403 sul CONNECT)"
        return False, f"{type(exc).__name__}: {text[:160]}"


# --------------------------------------------------------------------------- #
# GeoParquet helpers
# --------------------------------------------------------------------------- #
def write_gdf(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(path, index=False)


def read_gdf(path: Path) -> gpd.GeoDataFrame:
    return gpd.read_parquet(path)


def write_df(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)
