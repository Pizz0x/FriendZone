"""Scores for the standard combinations, aggregates per street and per
neighbourhood, and the GeoJSON/CSV exports."""

from __future__ import annotations

import json
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from model import scoring
from model.config import load_config, param_labels
from pipeline import params as params_mod
from pipeline.common import EXPORTS, PROCESSED, log

SCORES = PROCESSED / "scores.parquet"


def score_band(params: pd.DataFrame, band: str, profile: str, cfg: dict[str, Any] | None = None,
               strategy: str | None = None) -> pd.DataFrame:
    """S, colour class, reliability, cost per metre and worst parameters for one combination."""
    cfg = cfg or load_config()
    rows, X, available = params_mod.matrices(params, band, cfg)
    s = scoring.segment_scores(X, available, band, profile, rows["fattore_penalita"].to_numpy(), strategy=strategy, cfg=cfg)
    lam = scoring.profile_lambda(profile, cfg)
    worst = scoring.worst_parameters(X, available, band, profile, k=3, cfg=cfg)
    return pd.DataFrame({
        "segment_id": rows["segment_id"].to_numpy(),
        "fascia": band,
        "profilo": scoring.profile_key(profile, cfg),
        "S": np.round(s, 2),
        "classe_colore": scoring.color_class(s, cfg),
        "affidabilita": rows["affidabilita"].to_numpy(),
        "costo_per_m": np.round(scoring.path_cost(1.0, s, lam), 4),
        "peggiori": [",".join(w) for w in worst],
    })


def standard_scores(params: pd.DataFrame, cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    frames = [score_band(params, band, profile, cfg)
              for band in cfg["standard"]["bands"] for profile in cfg["standard"]["profiles"]]
    return pd.concat(frames, ignore_index=True)


def _weighted(values: pd.Series, weights: pd.Series) -> float:
    w = weights.to_numpy(dtype=float)
    v = values.to_numpy(dtype=float)
    ok = ~np.isnan(v)
    return float(np.sum(v[ok] * w[ok]) / np.sum(w[ok])) if ok.any() and np.sum(w[ok]) > 0 else float("nan")


def aggregate_streets(segments: pd.DataFrame, scores: pd.DataFrame) -> pd.DataFrame:
    """Per street (same name in the same neighbourhood) and combination."""
    df = scores.merge(segments[["segment_id", "via_id", "via", "quartiere", "lunghezza_m"]], on="segment_id")
    df["rosso_m"] = np.where(df["classe_colore"] == "rossa", df["lunghezza_m"], 0.0)
    df["Sxl"] = df["S"] * df["lunghezza_m"]
    df["Rxl"] = df["affidabilita"] * df["lunghezza_m"]
    g = df.groupby(["fascia", "profilo", "via_id"], sort=False)
    out = g.agg(via=("via", "first"), quartiere=("quartiere", "first"), tratti=("segment_id", "size"),
                lunghezza_m=("lunghezza_m", "sum"), Sxl=("Sxl", "sum"), S_min=("S", "min"),
                rosso_m=("rosso_m", "sum"), Rxl=("Rxl", "sum")).reset_index()
    out["S_medio"] = (out["Sxl"] / out["lunghezza_m"]).round(1)
    out["S_min"] = out["S_min"].round(1)
    out["pct_lunghezza_rossa"] = (100 * out["rosso_m"] / out["lunghezza_m"]).round(1)
    out["affidabilita_media"] = (out["Rxl"] / out["lunghezza_m"]).round(3)
    out["lunghezza_m"] = out["lunghezza_m"].round(1)
    out["classe_colore"] = scoring.color_class(out["S_medio"].to_numpy())
    cols = ["fascia", "profilo", "via_id", "via", "quartiere", "tratti", "lunghezza_m", "S_medio", "S_min",
            "pct_lunghezza_rossa", "classe_colore", "affidabilita_media"]
    return out[cols]


def aggregate_neighbourhoods(segments: pd.DataFrame, scores: pd.DataFrame, streets: pd.DataFrame,
                             exposed: pd.DataFrame | None = None, min_street_length_m: float = 100.0) -> pd.DataFrame:
    df = scores.merge(segments[["segment_id", "quartiere", "lunghezza_m"]], on="segment_id")
    df["rosso_m"] = np.where(df["classe_colore"] == "rossa", df["lunghezza_m"], 0.0)
    df["Sxl"] = df["S"] * df["lunghezza_m"]
    df["Rxl"] = df["affidabilita"] * df["lunghezza_m"]
    out = df.groupby(["fascia", "profilo", "quartiere"], sort=False).agg(
        tratti=("segment_id", "size"), lunghezza_km=("lunghezza_m", "sum"), Sxl=("Sxl", "sum"),
        rosso_m=("rosso_m", "sum"), Rxl=("Rxl", "sum")).reset_index()
    out["S_medio"] = (out["Sxl"] / out["lunghezza_km"]).round(1)
    out["pct_lunghezza_rossa"] = (100 * out["rosso_m"] / out["lunghezza_km"]).round(1)
    out["affidabilita_media"] = (out["Rxl"] / out["lunghezza_km"]).round(3)
    out["lunghezza_km"] = (out["lunghezza_km"] / 1000).round(2)
    named = streets[(streets["via"] != load_config()["network"]["unnamed_label"]) & (streets["lunghezza_m"] >= min_street_length_m)]
    worst = (named.sort_values("S_medio")
             .groupby(["fascia", "profilo", "quartiere"], sort=False)
             .apply(lambda g: "; ".join(f"{r.via} ({r.S_medio:.0f})" for r in g.head(5).itertuples()), include_groups=False)
             .rename("vie_peggiori").reset_index())
    out = out.merge(worst, on=["fascia", "profilo", "quartiere"], how="left")
    cols = ["fascia", "profilo", "quartiere", "tratti", "lunghezza_km", "S_medio", "pct_lunghezza_rossa",
            "affidabilita_media", "vie_peggiori"]
    if exposed is not None:
        out = out.merge(exposed, on=["fascia", "profilo", "quartiere"], how="left")
        cols += ["residenti_stimati", "residenti_esposti", "pct_residenti_esposti", "donne_esposte", "over60_esposti"]
    else:
        out["residenti_esposti"] = "n/d (mancano ISTAT e HRSL)"
        cols += ["residenti_esposti"]
    return out[cols]


EXPOSURE_RADIUS_M = 100.0


def exposure(segments: gpd.GeoDataFrame, scores: pd.DataFrame, quartieri: gpd.GeoDataFrame,
             population: gpd.GeoDataFrame | None, cfg: dict[str, Any]) -> pd.DataFrame | None:
    """Residents (total, women, 60+) living within 100 m of a red segment, per neighbourhood.

    Uses the Meta / CIESIN HRSL population grid (~30 m) as long as ISTAT census
    sections are not available; each pixel is counted once.
    """
    if population is None or not len(population):
        return None
    from shapely import STRtree

    metric = cfg["area"]["crs_metric"]
    pop = population.to_crs(metric).reset_index(drop=True)
    q = quartieri.to_crs(metric)
    pix_q = gpd.sjoin(pop[["geometry"]], q[["quartiere", "geometry"]], how="left", predicate="within")
    pix_q = pix_q[~pix_q.index.duplicated()]["quartiere"].reindex(pop.index)
    seg_geom = segments.set_index("segment_id").to_crs(metric).geometry
    tree = STRtree(pop.geometry.values)
    totals = pop.groupby(pix_q.values)[["popolazione", "donne", "over60"]].sum()
    rows = []
    for (band, profile), sc in scores.groupby(["fascia", "profilo"], sort=False):
        red = sc.loc[sc["classe_colore"] == "rossa", "segment_id"]
        hit = np.zeros(len(pop), dtype=bool)
        if len(red):
            pairs = tree.query(seg_geom.loc[red].values, predicate="dwithin", distance=EXPOSURE_RADIUS_M)
            hit[np.unique(pairs[1])] = True
        exp = pop[hit].groupby(pix_q[hit].values)[["popolazione", "donne", "over60"]].sum()
        exp = exp.reindex(totals.index, fill_value=0.0)
        for quartiere, r in exp.iterrows():
            tot = totals.loc[quartiere, "popolazione"]
            rows.append({"fascia": band, "profilo": profile, "quartiere": quartiere,
                         "residenti_stimati": int(round(tot)),
                         "residenti_esposti": int(round(r["popolazione"])),
                         "pct_residenti_esposti": round(100 * r["popolazione"] / tot, 1) if tot else 0.0,
                         "donne_esposte": int(round(r["donne"])), "over60_esposti": int(round(r["over60"]))})
    return pd.DataFrame(rows)


def export_geojson(segments: gpd.GeoDataFrame, scores: pd.DataFrame, cfg: dict[str, Any],
                   light_source: pd.DataFrame | None = None) -> list[str]:
    """One GeoJSON per standard combination, readable by kepler.gl and geojson.io.

    ``light_source`` (segment_id, fonte_luce) says where the light value comes
    from, so an estimate is never mistaken for a measurement.
    """
    colors = cfg["scoring"]["classes"]["colors"]
    labels = param_labels(cfg)
    metric = cfg["area"]["crs_metric"]
    geom = segments.to_crs(metric).geometry.simplify(0.5).to_crs("EPSG:4326")
    base = gpd.GeoDataFrame(segments[["segment_id", "via", "quartiere", "classe", "lunghezza_m"]].copy(), geometry=geom.values,
                            crs="EPSG:4326")
    if light_source is not None:
        base = base.merge(light_source, on="segment_id", how="left")
    written = []
    EXPORTS.mkdir(parents=True, exist_ok=True)
    for (band, profile), sc in scores.groupby(["fascia", "profilo"], sort=False):
        gdf = base.merge(sc.drop(columns=["fascia", "profilo"]), on="segment_id", how="inner")
        gdf["S"] = gdf["S"].round(1)
        gdf["colore"] = gdf["classe_colore"].map(colors)
        gdf["parametri_peggiori"] = gdf["peggiori"].map(lambda s: ", ".join(labels.get(k, k) for k in s.split(",") if k))
        gdf = gdf.drop(columns=["peggiori"])
        gdf["fascia"] = band
        gdf["profilo"] = profile
        path = EXPORTS / f"segments_{band}_{profile}.geojson"
        path.write_text(gdf.to_json(drop_id=True, to_wgs84=True, ensure_ascii=False), encoding="utf-8")
        written.append(path.name)
    _round_geojson_files(written)
    return written


def _round_geojson_files(names: list[str], digits: int = 5) -> None:
    """Round coordinates to ~1 m to keep the files small (full precision in the parquet)."""
    def rnd(c):
        return [rnd(v) for v in c] if isinstance(c, list) else round(c, digits)
    for name in names:
        path = EXPORTS / name
        data = json.loads(path.read_text(encoding="utf-8"))
        for f in data["features"]:
            f["geometry"]["coordinates"] = rnd(f["geometry"]["coordinates"])
        path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def run(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = cfg or load_config()
    segments = gpd.read_parquet(PROCESSED / "segments.parquet")
    params = pd.read_parquet(params_mod.PARAMS)
    scores = standard_scores(params, cfg)
    scores.to_parquet(SCORES, index=False)
    streets = aggregate_streets(segments, scores)
    from pipeline import segments as seg_mod
    from pipeline import sources_public

    exposed = exposure(segments, scores, seg_mod.load_quartieri(), sources_public.load_population_grid(cfg), cfg)
    quartieri = aggregate_neighbourhoods(segments, scores, streets, exposed)
    EXPORTS.mkdir(parents=True, exist_ok=True)
    streets.to_csv(EXPORTS / "vie.csv", index=False)
    quartieri.to_csv(EXPORTS / "quartieri.csv", index=False)
    first = params["fascia"].iloc[0]
    light_source = params.loc[params["fascia"] == first, ["segment_id", "fonte_luce"]] if "fonte_luce" in params else None
    files = export_geojson(segments, scores, cfg, light_source)
    log.info("export: %d GeoJSON, %d righe vie, %d righe quartieri", len(files), len(streets), len(quartieri))
    return {"scores": scores, "streets": streets, "quartieri": quartieri, "geojson": files}
