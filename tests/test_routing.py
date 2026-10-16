"""Navigator: least-cost routes on a small synthetic network (test data only)."""

import numpy as np
import pytest

from model import routing, scoring
from model.config import load_config


@pytest.fixture(scope="module")
def cfg():
    return load_config()


# A --200 m, S 20 (red)-- B
# A --150 m, S 90-- C --150 m, S 90-- B      (detour: 300 m, all green)
U = ["A", "A", "C"]
V = ["B", "C", "B"]
LENGTH = np.array([200.0, 150.0, 150.0])
SCORE = np.array([20.0, 90.0, 90.0])


def test_lambda_zero_is_shortest(cfg):
    r = routing.least_cost_route(U, V, LENGTH, SCORE, "A", "B", lam=0.0, cfg=cfg)
    assert r.nodes == ["A", "B"]
    assert r.length_m == 200
    assert r.red_m == 200


def test_high_lambda_takes_the_detour(cfg):
    # direct: 200 * (1 + 3 * 0.64) = 584; detour: 300 * (1 + 3 * 0.01) = 309
    r = routing.least_cost_route(U, V, LENGTH, SCORE, "A", "B", lam=3.0, cfg=cfg)
    assert r.nodes == ["A", "C", "B"]
    assert r.segments == [1, 2]
    assert r.length_m == 300
    assert r.red_m == 0
    assert r.cost == pytest.approx(float(scoring.path_cost(LENGTH[[1, 2]], SCORE[[1, 2]], 3.0).sum()))
    assert r.mean_score == pytest.approx(90)


def test_break_even_lambda(cfg):
    # 200 (1 + λ 0.64) = 300 (1 + λ 0.01)  ->  λ = 100 / 125 = 0.8
    assert routing.least_cost_route(U, V, LENGTH, SCORE, "A", "B", lam=0.7, cfg=cfg).nodes == ["A", "B"]
    assert routing.least_cost_route(U, V, LENGTH, SCORE, "A", "B", lam=0.9, cfg=cfg).nodes == ["A", "C", "B"]


def test_unreachable_and_same_node(cfg):
    assert routing.least_cost_route(U + ["X"], V + ["Y"], np.append(LENGTH, 10), np.append(SCORE, 50),
                                    "A", "Y", lam=1.0, cfg=cfg) is None
    r = routing.least_cost_route(U, V, LENGTH, SCORE, "A", "A", lam=1.0, cfg=cfg)
    assert r.nodes == ["A"] and r.length_m == 0


def test_route_lambda_and_speed(cfg):
    assert routing.route_lambda("donna", "medio", cfg) == pytest.approx(scoring.profile_lambda("donna", cfg))
    assert routing.route_lambda("donna", "molto", cfg) == pytest.approx(2 * scoring.profile_lambda("donna", cfg))
    assert routing.route_lambda(None, "poco", cfg) == pytest.approx(0.5 * cfg["scoring"]["lambda_base"])
    assert routing.walking_speed_kmh(None, cfg) == cfg["routing"]["walking_speed_kmh"]
    assert routing.walking_speed_kmh("donna+over75", cfg) == cfg["routing"]["slow_profiles"]["over75"]
