"""The 12 parameters for every segment and time band, with origin flags.

Each parameter is a value in [0, 1] (0 = worst, 1 = best) and a flag:
``measured`` (observed attribute), ``proxy`` (estimated or default values) or
``excluded`` (no public source). See ``config.yaml -> params`` for every
threshold. All geometry work is done in EPSG:32632 (metres).
"""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely import STRtree

from model import scoring, timebands
from model.config import load_config, param_keys
from pipeline import osm, pois, sources_public
from pipeline.common import PROCESSED, log

PARAMS = PROCESSED / "params.parquet"
PARAMS_META = PROCESSED / "params_meta.json"
M, P, E = scoring.MEASURED, scoring.PROXY, scoring.EXCLUDED


# --------------------------------------------------------------------------- #
# Spatial helpers (metric CRS)
# --------------------------------------------------------------------------- #
def _pairs(geoms: np.ndarray, others: np.ndarray, distance: float) -> np.ndarray:
    """(2, k) index pairs (geom_i, other_j) with distance(geom_i, other_j) <= distance."""
    if len(others) == 0 or len(geoms) == 0:
        return np.empty((2, 0), dtype=int)
    return STRtree(others).query(geoms, predicate="dwithin", distance=distance)


def _count(n: int, pairs: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    w = None if weights is None else weights[pairs[1]]
    return np.bincount(pairs[0], weights=w, minlength=n).astype(float)


def _nearest_distance(geoms: np.ndarray, others: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    if len(others) == 0:
        return np.full(len(geoms), np.inf), np.full(len(geoms), -1)
    idx, dist = STRtree(others).query_nearest(geoms, return_distance=True, all_matches=False)
    out_d = np.full(len(geoms), np.inf)
    out_i = np.full(len(geoms), -1)
    out_d[idx[0]] = dist
    out_i[idx[0]] = idx[1]
    return out_d, out_i


def _share_inside(lines: np.ndarray, polygons: np.ndarray) -> np.ndarray:
    """Share of each line's length inside the union of the given polygons."""
    share = np.zeros(len(lines))
    if len(polygons) == 0:
        return share
    pairs = STRtree(polygons).query(lines, predicate="intersects")
    if pairs.shape[1] == 0:
        return share
    inter = shapely.intersection(lines[pairs[0]], polygons[pairs[1]])
    inside = np.bincount(pairs[0], weights=shapely.length(inter), minlength=len(lines))
    return np.clip(inside / np.maximum(shapely.length(lines), 1e-9), 0.0, 1.0)


def _contains_any(series: pd.Series, values) -> np.ndarray:
    values = set(values)
    return series.fillna("").map(lambda s: bool(values & set(s.split(";")))).to_numpy()


# --------------------------------------------------------------------------- #
# Static context shared by all bands
# --------------------------------------------------------------------------- #
class Context:
    """Segments and OSM layers in metric CRS, plus static parameters."""

    def __init__(self, segments: gpd.GeoDataFrame, feats: gpd.GeoDataFrame, cfg: dict[str, Any]):
        self.cfg = cfg
        crs = cfg["area"]["crs_metric"]
        self.seg = segments.to_crs(crs).reset_index(drop=True)
        self.n = len(self.seg)
        self.lines = self.seg.geometry.values
        self.length = self.seg["lunghezza_m"].to_numpy(dtype=float)
        feats_m = feats.to_crs(crs)
        overture = sources_public.load_overture_places(cfg)
        self.overture = overture.to_crs(crs) if overture is not None else None
        self.activities = pois.activities(feats_m, cfg, extra=self.overture)
        self.help = pois.help_points(feats_m, cfg, extra=self.overture)
        viola = sources_public.load_punti_viola(cfg)
        if viola is not None and len(viola):
            self.help = pd.concat([self.help, viola.to_crs(crs)], ignore_index=True)
        self.stops = pois.transit_stops(feats_m)
        self.lamps = pois.street_lamps(feats_m)
        self.benches = pois.benches(feats_m)
        self.barriers = pois.barrier_lines(feats_m)
        self.rails = pois.rail_lines(feats_m)
        self.parks = pois.parks(feats_m, cfg)
        self.landuse = pois.landuse_polygons(feats_m, cfg)
        self.buildings = pois.residential_buildings(feats_m)
        self.all_buildings = pois.all_buildings(feats_m)
        self.sit_lamps = sources_public.load_lamps(cfg)
        self.residents = sources_public.load_istat_population(cfg)
        population = sources_public.load_population_grid(cfg)
        self.population = population.to_crs(crs) if population is not None else None
        self.park_share = _share_inside(self.lines, self.parks.geometry.values)
        self._park_index = self._nearest_park()
        log.info("contesto: %d tratti, %d attività (%d da Overture), %d punti di aiuto, %d fermate, %d lampioni OSM, "
                 "%d parchi, popolazione %s", self.n, len(self.activities),
                 int((self.activities.get("fonte") == "overture").sum()), len(self.help), len(self.stops),
                 len(self.lamps), len(self.parks), "HRSL" if self.population is not None else "non disponibile")

    def _nearest_park(self) -> np.ndarray:
        idx = np.full(self.n, -1)
        inside = self.park_share >= self.cfg["params"]["penalita"]["park_share_min"]
        if inside.any() and len(self.parks):
            mids = shapely.line_interpolate_point(self.lines[inside], 0.5, normalized=True)
            pairs = STRtree(self.parks.geometry.values).query(mids, predicate="within")
            first = pd.Series(pairs[1]).groupby(pairs[0]).first()
            sub = np.full(inside.sum(), -1)
            sub[first.index.to_numpy()] = first.to_numpy()
            idx[inside] = sub
        return idx


# --------------------------------------------------------------------------- #
# 1. Luce
# --------------------------------------------------------------------------- #
def _str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _lit_value(tag: str | None, values: dict[str, float]) -> float:
    tag = _str(tag)
    if not tag:
        return np.nan
    known = [values[v] for v in tag.split(";") if v in values]
    return float(np.mean(known)) if known else np.nan


def light(ctx: Context, samples: tuple[np.ndarray, np.ndarray] | None = None
          ) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict[str, Any]]:
    """Light value, flag, source label per segment and model metrics.

    Sources in order: SIT / City Green Light points > OSM ``lit`` > ``lit`` of
    an adjacent way > OSM street lamps (where mapped) > model estimate.
    """
    c = ctx.cfg["params"]["luce"]
    x = np.full(ctx.n, np.nan)
    flag = np.full(ctx.n, E, dtype=np.int8)
    source = np.full(ctx.n, "nessuna", dtype=object)

    if ctx.sit_lamps is not None and len(ctx.sit_lamps):
        pairs = _pairs(ctx.lines, ctx.sit_lamps.geometry.values, c["sit_lamp_buffer_m"])
        n_lamps = _count(ctx.n, pairs)
        x = np.minimum(1.0, n_lamps / (np.maximum(ctx.length, c["lamp_spacing_m"]) / c["lamp_spacing_m"]))
        return x, np.full(ctx.n, M, dtype=np.int8), np.full(ctx.n, "punti_luce_sit", dtype=object), {}

    lit_values = {str(k): float(v) for k, v in c["lit_values"].items()}
    tagged = np.array([_lit_value(t, lit_values) for t in ctx.seg["tag_lit"]])
    has = ~np.isnan(tagged)
    x[has], flag[has], source[has] = tagged[has], M, "osm_lit"

    # segments without lit inherit from a tagged way within a few metres
    todo = np.where(~has)[0]
    if len(todo) and has.any():
        mids = shapely.line_interpolate_point(ctx.lines[todo], 0.5, normalized=True)
        dist, near = _nearest_distance(mids, ctx.lines[has])
        ok = dist <= c["lit_inherit_distance_m"]
        x[todo[ok]] = tagged[has][near[ok]]
        flag[todo[ok]] = P
        source[todo[ok]] = "osm_lit_via_adiacente"

    # OSM street lamps (brief formula), only where at least one lamp is mapped on
    # the segment: OSM maps only part of the lamps, so their absence is not a datum
    todo = np.where(flag == E)[0]
    if len(todo) and len(ctx.lamps):
        lamps = ctx.lamps.geometry.values
        n_near = _count(len(todo), _pairs(ctx.lines[todo], lamps, c["osm_lamp_buffer_m"]))
        mapped = n_near >= 1
        spacing = c["lamp_spacing_m"]
        val = np.minimum(1.0, n_near / (np.maximum(ctx.length[todo], spacing) / spacing))
        x[todo[mapped]] = val[mapped]
        flag[todo[mapped]] = P
        source[todo[mapped]] = "lampioni_osm"

    # model estimate trained on the segments whose lit tag is known
    metrics: dict[str, Any] = {}
    todo = np.where(flag == E)[0]
    if len(todo) and c["model"].get("enabled", True) and samples is not None and has.sum() >= c["model"]["min_labels"]:
        from pipeline import light_model

        centre = gpd.GeoSeries.from_xy([c["model"]["centre_lon"]], [c["model"]["centre_lat"]], crs="EPSG:4326")
        cx, cy = centre.to_crs(ctx.cfg["area"]["crs_metric"]).iloc[0].coords[0]
        feats = light_model.features(ctx, samples, (cx, cy))
        y = np.where(has, (tagged >= 0.5).astype(float), np.nan)
        try:
            proba, metrics = light_model.train_and_predict(feats, y, ctx.seg["quartiere"].astype(str).to_numpy(), ctx.cfg)
            x[todo] = np.round(proba[todo], 3)
            flag[todo] = P
            source[todo] = "stima_modello"
        except ImportError:
            log.warning("scikit-learn non installato: niente stima della luce per i tratti senza dati")
    return x, flag, source, metrics


# --------------------------------------------------------------------------- #
# 4. Visuale libera (static part)
# --------------------------------------------------------------------------- #
def underpass_covered(ctx: Context) -> tuple[np.ndarray, np.ndarray]:
    pc = ctx.cfg["params"]["penalita"]
    seg = ctx.seg
    ped = seg["classe"].isin(pc["underpass_classes"]).to_numpy()
    tunnel = _contains_any(seg["tag_tunnel"], {"yes", "culvert", "avalanche_protector"})
    layer = seg["tag_layer"].fillna("").map(
        lambda s: any(v.lstrip("-").isdigit() and int(v) < 0 for v in s.split(";"))).to_numpy()
    underpass = (tunnel | layer) & ped
    covered_tag = seg["tag_covered"].fillna("")
    exempt = set(pc["covered_exempt_values"])
    covered = covered_tag.map(lambda s: any(v not in exempt and v not in {"", "no"} for v in s.split(";"))).to_numpy()
    covered = covered | _contains_any(seg["tag_tunnel"], {"building_passage"})
    return underpass, covered & ~underpass


def visibility(ctx: Context, underpass: np.ndarray, covered: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    c = ctx.cfg["params"]["visuale"]
    x = np.full(ctx.n, float(c["base"]))
    if len(ctx.barriers):
        bl = ctx.barriers.geometry.values
        weights = ctx.barriers["barrier"].map(c["barrier_weights"]).fillna(0.5).to_numpy()
        pairs = _pairs(ctx.lines, bl, c["barrier_buffer_m"])
        if pairs.shape[1]:
            buffers = shapely.buffer(ctx.lines[pairs[0]], c["barrier_buffer_m"], cap_style="flat")
            inside = shapely.length(shapely.intersection(bl[pairs[1]], buffers)) * weights[pairs[1]]
            share = np.minimum(1.0, np.bincount(pairs[0], weights=inside, minlength=ctx.n) / np.maximum(ctx.length, 1.0))
            x -= c["barrier_drop"] * share
    x -= c["covered_drop"] * covered
    x -= c["underpass_drop"] * underpass
    if len(ctx.rails):
        near_rail = _count(ctx.n, _pairs(ctx.lines, ctx.rails.geometry.values, c["railway_buffer_m"])) > 0
        x -= c["railway_drop"] * near_rail
    return np.clip(x, c["min_value"], 1.0), np.full(ctx.n, P, dtype=np.int8)


# --------------------------------------------------------------------------- #
# 5. Vie di fuga
# --------------------------------------------------------------------------- #
def escape_routes(ctx: Context) -> tuple[np.ndarray, np.ndarray]:
    c = ctx.cfg["params"]["vie_di_fuga"]
    su = ctx.seg["street_count_u"].to_numpy()
    sv = ctx.seg["street_count_v"].to_numpy()
    exits = (su >= 3).astype(float) + (sv >= 3).astype(float)
    rate = exits / np.maximum(ctx.length, c["min_length_m"]) * 100.0
    x = np.minimum(1.0, rate / c["target_per_100m"])
    x = np.where(ctx.length > c["long_segment_m"], x * c["long_segment_factor"], x)
    x = np.where(np.minimum(su, sv) <= 1, c["dead_end_value"], x)
    x = np.where(ctx.seg["classe"].eq("steps").to_numpy(), np.minimum(x, c["steps_max"]), x)
    return np.clip(x, 0.0, 1.0), np.full(ctx.n, M, dtype=np.int8)


# --------------------------------------------------------------------------- #
# 6. Uso del suolo
# --------------------------------------------------------------------------- #
def landuse_samples(ctx: Context) -> tuple[np.ndarray, np.ndarray]:
    """Land-use class index of sample points: (segment_index, class_or_-1)."""
    c = ctx.cfg["params"]["uso_suolo"]
    step = float(c["sample_step_m"])
    seg_idx, dists = [], []
    for i, L in enumerate(ctx.length):
        k = max(1, int(L // step))
        seg_idx.append(np.full(k, i))
        dists.append((np.arange(k) + 0.5) * L / k)
    seg_idx = np.concatenate(seg_idx)
    dists = np.concatenate(dists)
    lines = ctx.lines[seg_idx]
    p = shapely.get_coordinates(shapely.line_interpolate_point(lines, dists))
    p1 = shapely.get_coordinates(shapely.line_interpolate_point(lines, np.maximum(dists - 1.0, 0.0)))
    p2 = shapely.get_coordinates(shapely.line_interpolate_point(lines, np.minimum(dists + 1.0, ctx.length[seg_idx])))
    t = p2 - p1
    norm = np.linalg.norm(t, axis=1, keepdims=True)
    t = np.divide(t, norm, out=np.zeros_like(t), where=norm > 0)
    normal = np.column_stack([-t[:, 1], t[:, 0]])
    all_idx, all_pts = [], []
    for off in c["sample_offsets_m"]:
        all_idx.append(seg_idx)
        all_pts.append(p + off * normal)
    all_idx = np.concatenate(all_idx)
    pts = shapely.points(np.concatenate(all_pts))
    classes = np.full(len(pts), -1)
    if len(ctx.landuse):
        polys = ctx.landuse.geometry.values
        pairs = STRtree(polys).query(pts, predicate="within")
        if pairs.shape[1]:
            prio = ctx.landuse["priorita"].to_numpy()[pairs[1]]
            order = np.lexsort((prio, pairs[0]))
            pt_sorted, poly_sorted = pairs[0][order], pairs[1][order]
            first = np.r_[True, pt_sorted[1:] != pt_sorted[:-1]]
            classes[pt_sorted[first]] = poly_sorted[first]
    return all_idx, classes


def land_use(ctx: Context, samples: tuple[np.ndarray, np.ndarray], dark: bool) -> tuple[np.ndarray, np.ndarray]:
    c = ctx.cfg["params"]["uso_suolo"]
    seg_idx, poly_idx = samples
    names = ctx.landuse["classe_suolo"].to_numpy()

    def value(name: str) -> float:
        v = c["values"][name]
        return float(v["night" if dark else "day"]) if isinstance(v, dict) else float(v)

    lookup = {name: value(name) for name in c["values"]}
    classified = poly_idx >= 0
    vals = np.zeros(len(poly_idx))
    vals[classified] = [lookup[names[j]] for j in poly_idx[classified]]
    n_all = np.bincount(seg_idx, minlength=ctx.n)
    n_cls = np.bincount(seg_idx, weights=classified.astype(float), minlength=ctx.n)
    total = np.bincount(seg_idx, weights=vals, minlength=ctx.n)
    with np.errstate(invalid="ignore", divide="ignore"):
        x = total / n_cls
    ok = (n_cls / np.maximum(n_all, 1)) >= c["min_classified_share"]
    x = np.where(ok, x, np.nan)
    return x, np.where(ok, M, E).astype(np.int8)


# --------------------------------------------------------------------------- #
# 9. Qualità del percorso
# --------------------------------------------------------------------------- #
def _sidewalk_kind(row: pd.Series) -> str | None:
    vals = {k: _str(row.get(f"tag_{k}")) for k in ("sidewalk", "sidewalk_both", "sidewalk_left", "sidewalk_right")}
    sw = vals["sidewalk"].split(";")
    if "both" in sw or vals["sidewalk_both"] == "yes" or (vals["sidewalk_left"] == "yes" and vals["sidewalk_right"] == "yes"):
        return "both"
    if "left" in sw or "right" in sw or vals["sidewalk_left"] == "yes" or vals["sidewalk_right"] == "yes":
        return "left"
    if "no" in sw or "none" in sw or vals["sidewalk_both"] == "no":
        return "no"
    if "yes" in sw:
        return "yes"
    return None


def path_quality(ctx: Context) -> tuple[np.ndarray, np.ndarray]:
    c = ctx.cfg["params"]["percorso"]
    seg = ctx.seg
    x = np.full(ctx.n, np.nan)
    flag = np.full(ctx.n, P, dtype=np.int8)
    classe = seg["classe"].to_numpy()
    footway = seg["tag_footway"].fillna("").to_numpy()
    for i in range(ctx.n):
        cl = classe[i]
        fw = footway[i].split(";")[0] if footway[i] else ""
        if fw in c["footway_values"]:
            x[i], flag[i] = c["footway_values"][fw], M
        elif cl in c["pedestrian_classes"]:
            x[i], flag[i] = c["pedestrian_classes"][cl], M
        elif cl == "steps":
            x[i], flag[i] = c["steps_value"], M
        else:
            kind = _sidewalk_kind(seg.iloc[i]) if cl not in {"path", "track", "cycleway", "bridleway", "corridor"} else None
            group = "residential" if cl in {"residential", "living_street"} else (
                "major" if cl in c["major_classes"] else ("minor" if cl in c["minor_classes"] else None))
            if kind is not None and group is not None:
                table = {str(k): v for k, v in c["sidewalk_values"][group].items()}
                x[i], flag[i] = table["left" if kind in {"left", "right"} else kind], M
            else:
                x[i] = c["class_defaults"].get(cl, 0.5)
    rough = _contains_any(seg["tag_surface"], c["rough_surfaces"]) | _contains_any(seg["tag_smoothness"], c["bad_smoothness"])
    x = x - c["rough_surface_drop"] * rough
    if len(ctx.benches):
        n_b = _count(ctx.n, _pairs(ctx.lines, ctx.benches.geometry.values, c["bench_radius_m"]))
        x = x + np.minimum(c["bench_bonus_max"], c["bench_bonus_each"] * n_b)
    return np.clip(x, 0.0, 1.0), flag


# --------------------------------------------------------------------------- #
# Band-dependent parameters
# --------------------------------------------------------------------------- #
def residents_component(ctx: Context) -> np.ndarray:
    pc = ctx.cfg["params"]["persone"]
    r = pc["residents_radius_m"]
    if ctx.residents is not None and len(ctx.residents):
        # ISTAT 2021 census sections: residents within r metres, spread evenly over
        # each section's area, normalised on the 90th percentile
        sec = ctx.residents.to_crs(ctx.cfg["area"]["crs_metric"]).reset_index(drop=True)
        polys = sec.geometry.values
        dens = sec["popolazione"].to_numpy(dtype=float) / np.maximum(shapely.area(polys), 1.0)
        buffers = shapely.buffer(ctx.lines, r)
        pairs = STRtree(polys).query(buffers, predicate="intersects")
        inter = shapely.area(shapely.intersection(buffers[pairs[0]], polys[pairs[1]]))
        total = np.bincount(pairs[0], weights=inter * dens[pairs[1]], minlength=ctx.n)
        sat = np.percentile(total[total > 0], 90) if (total > 0).any() else 1.0
        ctx.residents_saturation = float(sat)
        ctx.residents_source = "ISTAT 2021 (sezioni di censimento)"
        return np.minimum(1.0, total / sat)
    if ctx.population is not None and len(ctx.population):
        # Meta / CIESIN HRSL: people living within r metres, normalised on the 90th percentile
        pop = ctx.population["popolazione"].to_numpy(dtype=float)
        total = _count(ctx.n, _pairs(ctx.lines, ctx.population.geometry.values, r), pop)
        sat = np.percentile(total[total > 0], 90) if (total > 0).any() else 1.0
        ctx.residents_saturation = float(sat)
        ctx.residents_source = "HRSL"
        return np.minimum(1.0, total / sat)
    if not len(ctx.buildings):
        return np.zeros(ctx.n)
    ctx.residents_source = "edifici OSM"
    b = ctx.buildings
    levels = pd.to_numeric(b.get("building:levels"), errors="coerce").clip(1, 15)
    default_levels = b["building"].map({"apartments": 4, "residential": 3, "house": 2, "detached": 2,
                                        "semidetached_house": 2, "terrace": 2, "dormitory": 3}).fillna(2)
    floor = (b.geometry.area * levels.fillna(default_levels)).to_numpy()
    centroids = b.geometry.centroid.values
    pairs = _pairs(ctx.lines, centroids, r)
    total = _count(ctx.n, pairs, floor)
    sat = np.percentile(total[total > 0], 90) if (total > 0).any() else 1.0
    ctx.residents_saturation = float(sat)
    return np.minimum(1.0, total / sat)


def band_parameters(ctx: Context, band: str, when: datetime, static: dict[str, Any]) -> dict[str, Any]:
    cfg = ctx.cfg
    pc, fc, hc, tc = (cfg["params"][k] for k in ("persone", "fronti_attivi", "punti_aiuto", "trasporto"))
    dark = timebands.is_dark(band, cfg)
    day_kind = timebands.day_type(when, cfg)
    n = ctx.n

    # activities open now
    act = ctx.activities
    open_now, measured_hours = pois.open_status(act, when, cfg)
    act_pts = act.geometry.values
    weights = open_now.astype(float)
    if day_kind == "weekend" and band in cfg["calendar"]["weekend_evening_bands"]:
        nightlife = act["categoria"].isin(pc["nightlife_categories"]).to_numpy()
        weights = weights * np.where(nightlife, pc["weekend_nightlife_factor"], 1.0)

    # 3. Fronti attivi
    pairs25 = _pairs(ctx.lines, act_pts, fc["radius_m"])
    n_open = _count(n, pairs25, open_now.astype(float))
    n_default = _count(n, pairs25, (~measured_hours).astype(float))
    rate = n_open / np.maximum(ctx.length, fc["min_length_m"]) * 100.0
    x_fronti = np.minimum(1.0, rate / fc["saturation_per_100m"])
    f_fronti = np.where(n_default > 0, P, M).astype(np.int8)

    # 12. Trasporto (also feeds the people proxy)
    stops = ctx.stops
    freq_table = tc["frequency_estimate"]
    freq = stops["modo"].map(lambda m: freq_table.get(m, freq_table["bus"])[band]).to_numpy(dtype=float)
    comfort = np.where(stops["comfort"].to_numpy(), 1.0, tc["no_shelter_factor"])
    pairs600 = _pairs(ctx.lines, stops.geometry.values, tc["zero_distance_m"])
    x_trasp = np.zeros(n)
    if pairs600.shape[1]:
        d = shapely.distance(ctx.lines[pairs600[0]], stops.geometry.values[pairs600[1]])
        dist_score = np.clip((tc["zero_distance_m"] - d) / (tc["zero_distance_m"] - tc["full_distance_m"]), 0.0, 1.0)
        val = dist_score * comfort[pairs600[1]] * freq[pairs600[1]]
        np.maximum.at(x_trasp, pairs600[0], val)
    f_trasp = np.where(_count(n, pairs600) > 0, P, M).astype(np.int8)  # frequency is an estimate (no GTFS)

    # 2. Persone (proxy)
    pairs50 = _pairs(ctx.lines, act_pts, pc["poi_radius_m"])
    a = np.minimum(1.0, _count(n, pairs50, weights) / pc["poi_saturation"])
    pairs100 = _pairs(ctx.lines, stops.geometry.values, pc["stop_radius_m"])
    f = np.minimum(1.0, _count(n, pairs100, freq) / pc["stop_saturation"])
    w = pc["weights"]
    x_pers = (w["attivita"] * a + w["fermate"] * f + w["residenti"] * static["residents"]) / (
        w["attivita"] + w["fermate"] + w["residenti"])
    if when.month in pc["park_winter_months"]:
        in_park = ctx.park_share >= cfg["params"]["penalita"]["park_share_min"]
        x_pers = np.where(in_park, x_pers * pc["park_winter_factor"], x_pers)

    # 11. Punti di aiuto
    hp = ctx.help
    help_open, help_measured = pois.open_status(hp, when, cfg)
    always = hp["categoria"].isin(["police", "hospital"]).to_numpy()
    open_pts = hp.geometry.values[help_open]
    dist, near = _nearest_distance(ctx.lines, open_pts)
    x_aiuto = np.clip(1.0 - (dist - hc["full_distance_m"]) / (hc["zero_distance_m"] - hc["full_distance_m"]), 0.0, 1.0)
    near_measured = np.ones(n, dtype=bool)  # no open help point within reach: distance is measured
    has_near = near >= 0
    if has_near.any():
        near_measured[has_near] = (help_measured | always)[help_open][near[has_near]]
    f_aiuto = np.where(near_measured | (dist > hc["zero_distance_m"]), M, P).astype(np.int8)

    # 6. Uso del suolo (day/night values for parks)
    x_suolo, f_suolo = land_use(ctx, static["landuse_samples"], dark)

    # Penalties
    blocking = static["blocking"]
    pen_park = np.zeros(n)
    if dark and len(ctx.parks):
        pk = cfg["params"]["penalita"]
        in_park = ctx._park_index >= 0
        park_hours = ctx.parks["opening_hours"] if "opening_hours" in ctx.parks else pd.Series([None] * len(ctx.parks))
        closed = np.array([pois.is_open(h, when) is False for h in park_hours])
        park_closed = np.where(in_park, closed[np.maximum(ctx._park_index, 0)], False)
        luce, f_luce = static["luce"]
        unlit = (f_luce != E) & (np.nan_to_num(luce, nan=1.0) < pk["park_unlit_threshold"])
        pen_park = np.where(in_park & (park_closed | unlit), cfg["scoring"]["penalties"]["park_dark"], 0.0)

    keys = param_keys(cfg)
    values = {
        "luce": static["luce"], "persone": (x_pers, np.full(n, P, dtype=np.int8)), "fronti_attivi": (x_fronti, f_fronti),
        "visuale": static["visuale"], "vie_di_fuga": static["vie_di_fuga"], "uso_suolo": (x_suolo, f_suolo),
        "episodi": (np.full(n, np.nan), np.full(n, E, dtype=np.int8)),
        "cura": (np.full(n, np.nan), np.full(n, E, dtype=np.int8)),
        "percorso": static["percorso"], "folla": (np.full(n, np.nan), np.full(n, E, dtype=np.int8)),
        "punti_aiuto": (x_aiuto, f_aiuto), "trasporto": (x_trasp, f_trasp),
    }
    X = np.column_stack([values[k][0] for k in keys])
    F = np.column_stack([values[k][1] for k in keys]).astype(np.int8)
    X = np.where(F == E, np.nan, X)
    return {"X": X, "F": F, "pen_bloccante": blocking, "pen_parco_buio": pen_park, "day_type": day_kind}


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def static_parameters(ctx: Context) -> dict[str, Any]:
    underpass, covered = underpass_covered(ctx)
    pk = ctx.cfg["params"]["penalita"]
    passage = ctx.seg["classe"].isin(pk["dead_end_classes"]).to_numpy() | (
        ctx.seg["classe"].eq("service").to_numpy() & _contains_any(ctx.seg["tag_service"], pk.get("dead_end_service_values", [])))
    dead_end_passage = ctx.seg["vicolo_cieco"].to_numpy() & passage
    blocking = np.where(underpass | covered | dead_end_passage, ctx.cfg["scoring"]["penalties"]["blocking"], 0.0)
    samples = landuse_samples(ctx)
    x_luce, f_luce, fonte_luce, light_metrics = light(ctx, samples)
    return {
        "luce": (x_luce, f_luce),
        "fonte_luce": fonte_luce,
        "light_model": light_metrics,
        "visuale": visibility(ctx, underpass, covered),
        "vie_di_fuga": escape_routes(ctx),
        "percorso": path_quality(ctx),
        "landuse_samples": samples,
        "residents": residents_component(ctx),
        "blocking": blocking,
        "underpass": underpass,
        "covered": covered,
        "dead_end_passage": dead_end_passage,
    }


def compute(segments: gpd.GeoDataFrame, feats: gpd.GeoDataFrame, cfg: dict[str, Any] | None = None,
            ref_date: date | None = None, bands: list[str] | None = None,
            people_norm: float | None = None) -> pd.DataFrame:
    """Long table: one row per (segment, band) with x_*, flag_*, penalties, reliability.

    ``people_norm`` is the city maximum used to normalise the people proxy; when
    None it is the configured percentile over all bands of ``ref_date`` (all
    five bands are then computed, even if only some are returned).
    """
    cfg = cfg or load_config()
    ref_date = ref_date or date.fromisoformat(cfg["standard"]["reference_date"])
    wanted = bands or list(cfg["timebands"]["order"])
    bands = wanted if people_norm is not None else list(cfg["timebands"]["order"])
    ctx = Context(segments, feats, cfg)
    static = static_parameters(ctx)
    keys = param_keys(cfg)
    results = {}
    for band in bands:
        when = timebands.band_time(band, ref_date, cfg)
        results[band] = (when, band_parameters(ctx, band, when, static))
    jp = keys.index("persone")
    if people_norm is None:
        raw = np.concatenate([res["X"][:, jp] for _, res in results.values()])
        people_norm = float(np.nanpercentile(raw, cfg["params"]["persone"]["normalize_percentile"])) or 1.0
    frames = []
    for band in wanted:
        when, res = results[band]
        res["X"][:, jp] = np.minimum(1.0, res["X"][:, jp] / people_norm)
        df = pd.DataFrame({"segment_id": ctx.seg["segment_id"].to_numpy(), "fascia": band,
                           "ora_riferimento": when.isoformat(), "tipo_giorno": res["day_type"]})
        for j, k in enumerate(keys):
            df[f"x_{k}"] = np.round(res["X"][:, j], 4)
            df[f"flag_{k}"] = pd.Categorical.from_codes(res["F"][:, j], categories=list(scoring.FLAGS))
        df["fonte_luce"] = static["fonte_luce"]
        df["pen_bloccante"] = res["pen_bloccante"]
        df["pen_parco_buio"] = res["pen_parco_buio"]
        df["fattore_penalita"] = scoring.penalty_factor(np.column_stack([res["pen_bloccante"], res["pen_parco_buio"]]))
        df["affidabilita"] = np.round(scoring.reliability(res["F"], band, cfg), 4)
        frames.append(df)
        log.info("parametri fascia %s (%s, %s) calcolati", band, when.strftime("%H:%M"), res["day_type"])
    out = pd.concat(frames, ignore_index=True)
    out.attrs["meta"] = {
        "reference_date": ref_date.isoformat(),
        "people_norm": people_norm,
        "residents_saturation": getattr(ctx, "residents_saturation", None),
        "residents_source": getattr(ctx, "residents_source", None),
        "luce_fonti": {k: int(v) for k, v in pd.Series(static["fonte_luce"]).value_counts().items()},
        "luce_modello": static["light_model"],
        "attivita": {"osm": int((ctx.activities["fonte"] == "osm").sum()),
                     "overture": int((ctx.activities["fonte"] == "overture").sum())},
        "punti_aiuto": {"osm": int((ctx.help.get("fonte") == "osm").sum()),
                        "overture": int((ctx.help.get("fonte") == "overture").sum())},
        "penalita": {"sottopassi": int(static["underpass"].sum()), "coperti": int(static["covered"].sum()),
                     "passaggi_senza_uscita": int(static["dead_end_passage"].sum())},
    }
    return out


def run(cfg: dict[str, Any] | None = None) -> pd.DataFrame:
    cfg = cfg or load_config()
    segments = gpd.read_parquet(PROCESSED / "segments.parquet")
    feats = osm.load_features()
    params = compute(segments, feats, cfg)
    meta = params.attrs.pop("meta")
    params.to_parquet(PARAMS, index=False)
    PARAMS_META.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log.info("salvati %d record di parametri in %s", len(params), PARAMS)
    return params


def matrices(params: pd.DataFrame, band: str, cfg: dict[str, Any] | None = None) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
    """Rows of a band plus the (n, 12) value matrix and availability mask."""
    cfg = cfg or load_config()
    keys = param_keys(cfg)
    rows = params[params["fascia"] == band].reset_index(drop=True)
    X = rows[[f"x_{k}" for k in keys]].to_numpy(dtype=float)
    F = np.column_stack([rows[f"flag_{k}"].astype(str).map(scoring.FLAG_CODE).to_numpy() for k in keys])
    return rows, X, F != E
