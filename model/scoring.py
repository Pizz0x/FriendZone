"""Scoring model: weights, profiles, segment score S, penalties, cost, reliability.

Formulas (brief, section 6.4):

* personalised weights  w_i = b_i(t) * prod_g m_{i,g} / sum_j b_j(t) * prod_g m_{j,g}
* segment score         S = 100 * sum_i w_i x_i * prod_k (1 - P_k)
* routing cost          C = L * (1 + lambda * ((100 - S) / 100) ** 2)
* reliability           R = sum_i b_i(t) * f(flag_i) / 100

Everything is vectorised over segments: parameter values are ``(n, 12)``
arrays in the order of ``config.yaml -> parameters``.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

import numpy as np

from model.config import load_config, param_keys

FLAGS = ("measured", "proxy", "excluded")
FLAG_CODE = {name: code for code, name in enumerate(FLAGS)}
MEASURED, PROXY, EXCLUDED = 0, 1, 2

_PROFILE_SPLIT = re.compile(r"[,+\s]+")


# --------------------------------------------------------------------------- #
# Profiles
# --------------------------------------------------------------------------- #
def parse_profiles(profiles: str | Iterable[str] | None, cfg: dict[str, Any] | None = None) -> tuple[str, ...]:
    """Normalise a profile selection into a canonical tuple (config order).

    Accepts ``"donna+giovani_16_34"``, ``"donna,over75"``, a list, or ``None``.
    ``riferimento`` is dropped when combined with other profiles because it has
    no multipliers; an empty selection means ``("riferimento",)``.
    """
    cfg = cfg or load_config()
    if profiles is None:
        items: list[str] = []
    elif isinstance(profiles, str):
        items = [p for p in _PROFILE_SPLIT.split(profiles.strip()) if p]
    else:
        items = [p for p in profiles if p]
    known = list(cfg["profiles"])
    unknown = [p for p in items if p not in known]
    if unknown:
        raise ValueError(f"profilo sconosciuto: {', '.join(unknown)} (validi: {', '.join(known)})")
    chosen = {p for p in items if p != "riferimento"}
    if not chosen:
        return ("riferimento",)
    return tuple(p for p in known if p in chosen)


def profile_key(profiles: str | Iterable[str] | None, cfg: dict[str, Any] | None = None) -> str:
    """Canonical string for a profile combination, e.g. ``donna+giovani_16_34``."""
    return "+".join(parse_profiles(profiles, cfg))


def profile_multipliers(profiles: str | Iterable[str] | None, cfg: dict[str, Any] | None = None) -> np.ndarray:
    """Product of the weight multipliers of all selected profiles, shape (12,)."""
    cfg = cfg or load_config()
    keys = param_keys(cfg)
    mult = np.ones(len(keys))
    for name in parse_profiles(profiles, cfg):
        for param, factor in (cfg["profiles"][name].get("multipliers") or {}).items():
            mult[keys.index(param)] *= float(factor)
    return mult


def profile_lambda(profiles: str | Iterable[str] | None, cfg: dict[str, Any] | None = None) -> float:
    """Risk sensitivity: lambda_base times the product of the profile factors."""
    cfg = cfg or load_config()
    lam = float(cfg["scoring"]["lambda_base"])
    for name in parse_profiles(profiles, cfg):
        lam *= float(cfg["profiles"][name].get("lambda_factor", 1.0))
    return lam


# --------------------------------------------------------------------------- #
# Weights
# --------------------------------------------------------------------------- #
def base_weights(band: str, cfg: dict[str, Any] | None = None) -> np.ndarray:
    """Base weights b_i(t) of a time band, shape (12,), summing to 100.

    ``day``/``night`` columns come from the parameter table; ``blend`` mixes
    them (prima ora di buio: 50/50). Band multipliers (notte fonda: persone
    x1.3) are applied and the result is renormalised to 100.
    """
    cfg = cfg or load_config()
    bands = cfg["timebands"]["bands"]
    if band not in bands:
        raise ValueError(f"fascia sconosciuta: {band} (valide: {', '.join(bands)})")
    spec = bands[band]
    day = np.array([p["weight_day"] for p in cfg["parameters"]], dtype=float)
    night = np.array([p["weight_night"] for p in cfg["parameters"]], dtype=float)
    kind = spec["weights"]
    if kind == "day":
        b = day
    elif kind == "night":
        b = night
    elif kind == "blend":
        share = float(spec.get("day_share", 0.5))
        b = share * day + (1.0 - share) * night
    else:
        raise ValueError(f"tipo di pesi non valido per {band}: {kind}")
    keys = param_keys(cfg)
    b = b.copy()
    for param, factor in (spec.get("multipliers") or {}).items():
        b[keys.index(param)] *= float(factor)
    return 100.0 * b / b.sum()


def raw_weights(band: str, profiles: str | Iterable[str] | None = None, cfg: dict[str, Any] | None = None) -> np.ndarray:
    """Unnormalised personalised weights b_i(t) * prod m_{i,g}."""
    cfg = cfg or load_config()
    return base_weights(band, cfg) * profile_multipliers(profiles, cfg)


def personalized_weights(band: str, profiles: str | Iterable[str] | None = None, cfg: dict[str, Any] | None = None) -> np.ndarray:
    """Personalised weights w_i normalised to sum 1 (all parameters available)."""
    w = raw_weights(band, profiles, cfg)
    return w / w.sum()


def effective_weights(raw: np.ndarray, available: np.ndarray, strategy: str = "renormalize") -> np.ndarray:
    """Weights actually applied to each segment, shape like ``available``.

    With ``renormalize`` excluded parameters get weight 0 and the others are
    rescaled to sum 1; with ``neutral`` all parameters keep their weight.
    """
    available = np.asarray(available, dtype=bool)
    raw = np.broadcast_to(np.asarray(raw, dtype=float), available.shape)
    if strategy == "neutral":
        return raw / raw.sum(axis=-1, keepdims=True)
    if strategy != "renormalize":
        raise ValueError(f"unmeasured_strategy non valida: {strategy}")
    w = np.where(available, raw, 0.0)
    total = w.sum(axis=-1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(total > 0, w / total, np.nan)


# --------------------------------------------------------------------------- #
# Score, penalties, cost, classes
# --------------------------------------------------------------------------- #
def penalty_factor(penalties: np.ndarray | Sequence[float] | None, n: int | None = None) -> np.ndarray:
    """prod_k (1 - P_k). ``penalties`` is (n, K) or (K,) with P_k in [0, 1]."""
    if penalties is None:
        return np.ones(n or 1)
    p = np.clip(np.asarray(penalties, dtype=float), 0.0, 1.0)
    if p.ndim == 1:
        p = p[None, :] if n is None else np.broadcast_to(p, (n, p.shape[0]))
    return np.prod(1.0 - p, axis=1)


def segment_scores(
    x: np.ndarray,
    available: np.ndarray | None,
    band: str,
    profiles: str | Iterable[str] | None = None,
    penalty: np.ndarray | float | None = None,
    *,
    strategy: str | None = None,
    cfg: dict[str, Any] | None = None,
) -> np.ndarray:
    """Score S in [0, 100] for each segment.

    x          (n, 12) parameter values in [0, 1]; NaN where excluded.
    available  (n, 12) bool, False for excluded parameters (None = all).
    penalty    (n,) multiplicative factor prod(1 - P_k), default 1.
    """
    cfg = cfg or load_config()
    x = np.atleast_2d(np.asarray(x, dtype=float))
    available = np.ones_like(x, dtype=bool) if available is None else np.atleast_2d(np.asarray(available, dtype=bool))
    strategy = strategy or cfg["scoring"]["unmeasured_strategy"]
    if strategy == "neutral":
        x = np.where(available, x, float(cfg["scoring"]["neutral_value"]))
        available_for_weights = np.ones_like(available)
    else:
        x = np.where(available, x, 0.0)
        available_for_weights = available
    w = effective_weights(raw_weights(band, profiles, cfg), available_for_weights, strategy)
    s = np.nansum(w * np.clip(x, 0.0, 1.0), axis=1)
    s = np.where(np.isnan(w).all(axis=1), np.nan, s)
    factor = np.ones(x.shape[0]) if penalty is None else np.broadcast_to(np.asarray(penalty, dtype=float), (x.shape[0],))
    return np.clip(100.0 * s * factor, 0.0, 100.0)


def path_cost(length: np.ndarray | float, score: np.ndarray | float, lam: float) -> np.ndarray | float:
    """C = L * (1 + lambda * ((100 - S) / 100) ** 2)."""
    s = np.asarray(score, dtype=float)
    return np.asarray(length, dtype=float) * (1.0 + lam * ((100.0 - s) / 100.0) ** 2)


def color_class(score: np.ndarray | float, cfg: dict[str, Any] | None = None) -> np.ndarray:
    """'rossa' below 40, 'gialla' from 40 to 65, 'verde' above 65."""
    cfg = cfg or load_config()
    c = cfg["scoring"]["classes"]
    s = np.asarray(score, dtype=float)
    out = np.where(s < c["red_below"], "rossa", np.where(s > c["green_above"], "verde", "gialla"))
    return np.where(np.isnan(s), "n/d", out)


# --------------------------------------------------------------------------- #
# Reliability and diagnostics
# --------------------------------------------------------------------------- #
def flag_codes(flags: np.ndarray | Sequence[Sequence[str]]) -> np.ndarray:
    """Convert flag names to int codes (0 measured, 1 proxy, 2 excluded)."""
    arr = np.asarray(flags)
    if arr.dtype.kind in "iu":
        return arr.astype(np.int8)
    lookup = np.vectorize(FLAG_CODE.__getitem__, otypes=[np.int8])
    return lookup(arr)


def reliability(flags: np.ndarray, band: str, cfg: dict[str, Any] | None = None) -> np.ndarray:
    """R = sum_i b_i(t) * factor(flag_i) / 100 with factors 1 / 0.5 / 0."""
    cfg = cfg or load_config()
    codes = np.atleast_2d(flag_codes(flags))
    f = cfg["scoring"]["reliability_factors"]
    factors = np.array([f["measured"], f["proxy"], f["excluded"]], dtype=float)[codes]
    return (factors * base_weights(band, cfg)).sum(axis=1) / 100.0


def weighted_losses(x: np.ndarray, available: np.ndarray, band: str, profiles=None, *, strategy: str | None = None, cfg=None) -> np.ndarray:
    """Points lost by each parameter: 100 * w_i * (1 - x_i), (n, 12); NaN if excluded."""
    cfg = cfg or load_config()
    strategy = strategy or cfg["scoring"]["unmeasured_strategy"]
    x = np.atleast_2d(np.asarray(x, dtype=float))
    available = np.atleast_2d(np.asarray(available, dtype=bool))
    w = effective_weights(raw_weights(band, profiles, cfg), available if strategy == "renormalize" else np.ones_like(available), strategy)
    loss = 100.0 * w * (1.0 - np.clip(np.nan_to_num(x, nan=0.0), 0.0, 1.0))
    return np.where(available, loss, np.nan)


def worst_parameters(x: np.ndarray, available: np.ndarray, band: str, profiles=None, k: int = 3, cfg=None) -> list[list[str]]:
    """Names of the k available parameters that lower S the most, per segment."""
    cfg = cfg or load_config()
    keys = np.array(param_keys(cfg))
    loss = np.nan_to_num(weighted_losses(x, available, band, profiles, cfg=cfg), nan=-1.0)
    order = np.argsort(-loss, axis=1)[:, :k]
    return [[str(keys[j]) for j in row if loss[i, j] > 0] for i, row in enumerate(order)]
