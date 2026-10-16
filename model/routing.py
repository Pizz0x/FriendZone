"""Least-cost walking routes on the segment graph (navigator of the citizens' app).

The cost of a segment is the one of the brief (6.4):
``C = L * (1 + lambda * ((100 - S) / 100) ** 2)``. With ``lambda = 0`` the route
is simply the shortest one; the larger lambda, the longer the detour a person
accepts to stay on streets with a higher S. The browser app runs the same
algorithm in JavaScript (``frontend/src/core.js``); ``tests/test_frontend_js.py``
checks that the two agree.
"""

from __future__ import annotations

import heapq
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Hashable, Iterable, Sequence

import numpy as np

from model import scoring
from model.config import load_config


@dataclass
class Route:
    nodes: list[Hashable]      # graph nodes in walking order
    segments: list[int]        # row index of each segment walked, in order
    length_m: float
    cost: float
    red_m: float               # metres on segments of the red class
    mean_score: float          # S averaged over the length


def build_graph(u: Sequence[Hashable], v: Sequence[Hashable]) -> dict[Hashable, list[tuple[Hashable, int]]]:
    """Undirected adjacency: node -> [(neighbour, segment index)]."""
    adj: dict[Hashable, list[tuple[Hashable, int]]] = defaultdict(list)
    for i, (a, b) in enumerate(zip(u, v)):
        adj[a].append((b, i))
        if a != b:
            adj[b].append((a, i))
    return adj


def segment_costs(length: np.ndarray, score: np.ndarray, lam: float) -> np.ndarray:
    return np.asarray(scoring.path_cost(length, score, lam), dtype=float)


def least_cost_route(u: Sequence[Hashable], v: Sequence[Hashable], length: np.ndarray, score: np.ndarray,
                     source: Hashable, target: Hashable, lam: float,
                     cfg: dict[str, Any] | None = None,
                     adj: dict[Hashable, list[tuple[Hashable, int]]] | None = None) -> Route | None:
    """Dijkstra from ``source`` to ``target``; ``None`` if they are not connected."""
    cfg = cfg or load_config()
    length = np.asarray(length, dtype=float)
    score = np.asarray(score, dtype=float)
    adj = adj if adj is not None else build_graph(u, v)
    cost = segment_costs(length, score, lam)
    best = {source: 0.0}
    prev: dict[Hashable, tuple[Hashable, int]] = {}
    heap: list[tuple[float, int, Hashable]] = [(0.0, 0, source)]
    counter = 1  # tie-breaker, so nodes never need to be comparable
    done = set()
    while heap:
        c, _, node = heapq.heappop(heap)
        if node in done:
            continue
        done.add(node)
        if node == target:
            break
        for nb, seg in adj.get(node, ()):
            nc = c + cost[seg]
            if nc < best.get(nb, np.inf):
                best[nb] = nc
                prev[nb] = (node, seg)
                heapq.heappush(heap, (nc, counter, nb))
                counter += 1
    if target not in best:
        return None
    nodes, segs = [target], []
    while nodes[-1] != source:
        node, seg = prev[nodes[-1]]
        nodes.append(node)
        segs.append(seg)
    nodes.reverse()
    segs.reverse()
    return summarize(nodes, segs, length, score, lam, cfg)


def summarize(nodes: list[Hashable], segs: Iterable[int], length: np.ndarray, score: np.ndarray,
              lam: float, cfg: dict[str, Any] | None = None) -> Route:
    cfg = cfg or load_config()
    segs = list(segs)
    red_below = cfg["scoring"]["classes"]["red_below"]
    L = length[segs] if segs else np.zeros(0)
    s = score[segs] if segs else np.zeros(0)
    total = float(L.sum())
    return Route(nodes=nodes, segments=segs, length_m=total,
                 cost=float(segment_costs(L, s, lam).sum()),
                 red_m=float(L[s < red_below].sum()),
                 mean_score=float((L * s).sum() / total) if total > 0 else float("nan"))


def route_lambda(profiles: str | Iterable[str] | None, preference: str = "medio",
                 cfg: dict[str, Any] | None = None) -> float:
    """lambda of the profile times the detour preference chosen in the app."""
    cfg = cfg or load_config()
    factor = float(cfg["routing"]["detour_preference"][preference])
    return scoring.profile_lambda(profiles, cfg) * factor


def walking_speed_kmh(profiles: str | Iterable[str] | None, cfg: dict[str, Any] | None = None) -> float:
    cfg = cfg or load_config()
    r = cfg["routing"]
    speeds = [float(r["walking_speed_kmh"])]
    speeds += [float(r["slow_profiles"][p]) for p in scoring.parse_profiles(profiles, cfg) if p in r["slow_profiles"]]
    return min(speeds)
