"""Estimate of street lighting where OSM has no ``lit`` information.

A gradient-boosting classifier is trained on the segments whose ``lit`` tag is
known, using only context features available on every segment: road class,
nearby buildings and population, land use, parks, unpaved surface, mapped
street lamps, distance from the centre. Its probability of "lit" becomes the
light value of the remaining segments, with flag ``proxy`` and source
``stima_modello``. Cross-validation is grouped by neighbourhood, so the
reported accuracy is measured on areas the model has not seen.

This is an estimate, not a measurement: it is replaced segment by segment as
soon as real data (SIT / City Green Light light points, new ``lit`` tags,
citizen reports) are available.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import shapely

CLASSES = ["primary", "secondary", "tertiary", "unclassified", "residential", "living_street", "service",
           "pedestrian", "footway", "path", "track", "steps", "cycleway"]
LANDUSE_GROUPS = {
    "urbano": {"residential", "commercial", "retail", "mixed", "education", "institutional", "civic", "religious"},
    "produttivo": {"industrial", "railway", "depot", "construction", "brownfield", "landfill", "military", "quarry"},
    "agricolo_naturale": {"farmland", "farmyard", "meadow", "orchard", "vineyard", "grass", "forest", "wood", "scrub",
                          "allotments", "greenfield", "cemetery"},
    "parco_sport": {"park", "sport"},
    "parcheggio": {"parking"},
}


def features(ctx, landuse_samples: tuple[np.ndarray, np.ndarray], centre_xy: tuple[float, float]) -> pd.DataFrame:
    """Context features for every segment of ``ctx`` (a params.Context)."""
    from pipeline.params import _contains_any, _count, _pairs

    seg = ctx.seg
    n = ctx.n
    cols: dict[str, np.ndarray] = {}
    classe = seg["classe"].to_numpy()
    for c in CLASSES:
        cols[f"classe_{c}"] = (classe == c).astype(float)
    cols["log_lunghezza"] = np.log1p(ctx.length)
    mids = shapely.line_interpolate_point(ctx.lines, 0.5, normalized=True)
    cx, cy = centre_xy
    xy = shapely.get_coordinates(mids)
    cols["dist_centro_km"] = np.hypot(xy[:, 0] - cx, xy[:, 1] - cy) / 1000.0
    if len(ctx.all_buildings):
        cols["edifici_50m"] = _count(n, _pairs(ctx.lines, ctx.all_buildings.geometry.centroid.values, 50.0))
    else:
        cols["edifici_50m"] = np.zeros(n)
    if ctx.population is not None and len(ctx.population):
        pop = ctx.population["popolazione"].to_numpy(dtype=float)
        cols["popolazione_100m"] = _count(n, _pairs(ctx.lines, ctx.population.geometry.values, 100.0), pop)
    else:
        cols["popolazione_100m"] = np.zeros(n)
    cols["lampioni_30m"] = _count(n, _pairs(ctx.lines, ctx.lamps.geometry.values, 30.0)) if len(ctx.lamps) else np.zeros(n)
    cols["quota_parco"] = ctx.park_share
    rough = ctx.cfg["params"]["percorso"]["rough_surfaces"]
    cols["sterrato"] = _contains_any(seg["tag_surface"], rough).astype(float)
    cols["tag_marciapiede"] = seg[[c for c in seg.columns if c.startswith("tag_sidewalk")]].notna().any(axis=1).to_numpy(dtype=float)
    cols["marciapiede_separato"] = _contains_any(seg["tag_footway"], {"sidewalk", "crossing"}).astype(float)

    seg_idx, poly_idx = landuse_samples
    names = ctx.landuse["classe_suolo"].to_numpy()
    n_all = np.bincount(seg_idx, minlength=n).astype(float)
    for group, members in LANDUSE_GROUPS.items():
        hit = np.zeros(len(poly_idx), dtype=float)
        ok = poly_idx >= 0
        hit[ok] = [names[j] in members for j in poly_idx[ok]]
        cols[f"suolo_{group}"] = np.bincount(seg_idx, weights=hit, minlength=n) / np.maximum(n_all, 1)
    return pd.DataFrame(cols)


def train_and_predict(X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, cfg: dict[str, Any]) -> tuple[np.ndarray, dict[str, Any]]:
    """Fit on labelled rows (y in {0, 1}, NaN elsewhere); return P(lit) for every row and CV metrics."""
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import accuracy_score, brier_score_loss, roc_auc_score
    from sklearn.model_selection import GroupKFold

    mcfg = cfg["params"]["luce"]["model"]
    labelled = ~np.isnan(y)
    Xl, yl, gl = X[labelled].to_numpy(), y[labelled].astype(int), groups[labelled]

    def make():
        return HistGradientBoostingClassifier(max_iter=int(mcfg["max_iter"]), learning_rate=float(mcfg["learning_rate"]),
                                              max_leaf_nodes=int(mcfg["max_leaf_nodes"]),
                                              l2_regularization=float(mcfg["l2_regularization"]), random_state=0)

    n_groups = len(np.unique(gl))
    folds = min(int(mcfg["cv_folds"]), n_groups)
    oof = np.full(len(yl), np.nan)
    if folds >= 2 and len(np.unique(yl)) == 2:
        for train, test in GroupKFold(n_splits=folds).split(Xl, yl, gl):
            if len(np.unique(yl[train])) < 2:
                continue
            oof[test] = make().fit(Xl[train], yl[train]).predict_proba(Xl[test])[:, 1]
    ok = ~np.isnan(oof)
    metrics: dict[str, Any] = {"tratti_etichettati": int(labelled.sum()), "illuminati": int(yl.sum()),
                               "non_illuminati": int((yl == 0).sum()), "fold": folds,
                               "validazione": "GroupKFold per quartiere"}
    if ok.any() and len(np.unique(yl[ok])) == 2:
        metrics.update({
            "auc": round(float(roc_auc_score(yl[ok], oof[ok])), 3),
            "accuratezza": round(float(accuracy_score(yl[ok], oof[ok] >= 0.5)), 3),
            "accuratezza_baseline_sempre_illuminato": round(float(yl[ok].mean()), 3),
            "brier": round(float(brier_score_loss(yl[ok], oof[ok])), 4),
            "recall_non_illuminati": round(float(((oof[ok] < 0.5) & (yl[ok] == 0)).sum() / max((yl[ok] == 0).sum(), 1)), 3),
        })
    model = make().fit(Xl, yl)
    proba = model.predict_proba(X.to_numpy())[:, 1]
    metrics["quota_stimata_illuminata"] = round(float((proba[~labelled] >= 0.5).mean()), 3) if (~labelled).any() else None
    return proba, metrics
