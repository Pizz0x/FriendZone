"""Tests of the scoring model (brief, section 6.7)."""

import numpy as np
import pytest

from model import scoring
from model.config import load_config, param_keys

CFG = load_config()
KEYS = param_keys(CFG)

# PDF example, "sera" band, values in the order of the 12 parameters
A = [0.8, 0.7, 0.7, 0.8, 0.9, 0.9, 0.8, 0.8, 0.9, 0.7, 0.8, 0.6]
B = [0.5, 0.3, 0.2, 0.5, 0.6, 0.4, 0.3, 0.5, 0.7, 0.2, 0.5, 0.7]
C = [0.4, 0.2, 0.1, 0.3, 0.3, 0.5, 0.4, 0.6, 0.5, 0.3, 0.3, 0.3]
PENALTY_C = scoring.penalty_factor([0.30])[0]


def score(x, profile="riferimento", band="sera", penalty=1.0, available=None, strategy="renormalize"):
    return float(scoring.segment_scores(np.array([x]), available, band, profile, np.array([penalty]), strategy=strategy)[0])


# --------------------------------------------------------------------------- #
# PDF example (all measured, no renormalisation)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "x, penalty, expected_s, expected_cost",
    [(A, 1.0, 79, 1.07), (B, 1.0, 42, 1.50), (C, PENALTY_C, 23, 1.88)],
    ids=["A_corso_Palladio", "B_viale_Roma", "C_rampa_via_Gorizia"],
)
def test_pdf_example_reference_profile(x, penalty, expected_s, expected_cost):
    s = score(x, penalty=penalty)
    assert s == pytest.approx(expected_s, abs=0.6)
    lam = scoring.profile_lambda("riferimento")
    assert lam == pytest.approx(1.5)
    assert float(scoring.path_cost(1.0, s, lam)) == pytest.approx(expected_cost, abs=0.01)


def test_pdf_example_c_200m_woman_over75():
    lam = scoring.profile_lambda("donna+over75")
    assert lam == pytest.approx(3.9)
    s = score(C, profile="donna+over75", penalty=PENALTY_C)
    cost = float(scoring.path_cost(200.0, s, lam))
    assert cost == pytest.approx(646, rel=0.02)


@pytest.mark.parametrize(
    "profile, x, penalty, expected_s, expected_cost_per_m",
    [
        ("donna+giovani_16_34", A, 1.0, 79, 1.14),
        ("donna+giovani_16_34", B, 1.0, 42, 2.01),
        ("donna+giovani_16_34", C, PENALTY_C, 24, 2.75),
        ("donna+over75", A, 1.0, 79, 1.16),
        ("donna+over75", B, 1.0, 44, 2.23),
        ("donna+over75", C, PENALTY_C, 24, 3.23),
    ],
)
def test_pdf_example_full_table(profile, x, penalty, expected_s, expected_cost_per_m):
    s = score(x, profile=profile, penalty=penalty)
    assert s == pytest.approx(expected_s, abs=0.6)
    lam = scoring.profile_lambda(profile)
    assert float(scoring.path_cost(1.0, s, lam)) == pytest.approx(expected_cost_per_m, abs=0.015)


# --------------------------------------------------------------------------- #
# Weights and profiles
# --------------------------------------------------------------------------- #
def test_base_weights_sum_to_100_for_every_band():
    for band in CFG["timebands"]["bands"]:
        assert scoring.base_weights(band).sum() == pytest.approx(100.0)


def test_twilight_weights_are_day_night_average():
    day = scoring.base_weights("giorno")
    night = scoring.base_weights("sera")
    assert scoring.base_weights("prima_ora_buio") == pytest.approx(0.5 * day + 0.5 * night)


def test_deep_night_boosts_people_then_renormalises():
    w = scoring.base_weights("notte_fonda")
    i = KEYS.index("persone")
    assert w[i] == pytest.approx(100 * 14 * 1.3 / (100 + 14 * 0.3))
    assert w.sum() == pytest.approx(100.0)


def test_light_weighs_much_less_by_day():
    i = KEYS.index("luce")
    assert scoring.personalized_weights("giorno")[i] < 0.25 * scoring.personalized_weights("sera")[i]


def test_profile_combination_multiplies_and_renormalises():
    m = scoring.profile_multipliers("donna+over75")
    assert m[KEYS.index("luce")] == pytest.approx(1.3 * 1.2)
    assert m[KEYS.index("percorso")] == pytest.approx(2.5)
    assert m[KEYS.index("folla")] == pytest.approx(1.6)
    w = scoring.personalized_weights("sera", "donna+over75")
    assert w.sum() == pytest.approx(1.0)
    raw = scoring.base_weights("sera") * m
    assert w == pytest.approx(raw / raw.sum())


def test_profile_parsing_is_order_insensitive_and_drops_reference():
    assert scoring.parse_profiles("over75,donna") == ("donna", "over75")
    assert scoring.parse_profiles("donna over75") == ("donna", "over75")
    assert scoring.parse_profiles(["riferimento", "donna"]) == ("donna",)
    assert scoring.parse_profiles(None) == ("riferimento",)
    assert scoring.profile_key("giovani_16_34+donna") == "donna+giovani_16_34"
    with pytest.raises(ValueError):
        scoring.parse_profiles("astronauta")


def test_lambda_combinations():
    assert scoring.profile_lambda("donna") == pytest.approx(3.0)
    assert scoring.profile_lambda("donna+giovani_16_34") == pytest.approx(3.0)
    assert scoring.profile_lambda("donna+in_compagnia") == pytest.approx(1.5)
    assert scoring.profile_lambda("conosce_zona") == pytest.approx(1.2)


# --------------------------------------------------------------------------- #
# Excluded parameters
# --------------------------------------------------------------------------- #
def _public_only_availability():
    available = np.ones(12, dtype=bool)
    for key in ("episodi", "cura", "folla"):
        available[KEYS.index(key)] = False
    return available


def test_renormalisation_ignores_excluded_parameters():
    available = _public_only_availability()
    x = np.array(A, dtype=float)
    x_garbage = x.copy()
    x_garbage[~available] = np.nan
    b = scoring.base_weights("sera")
    expected = 100 * (b[available] * x[available]).sum() / b[available].sum()
    assert score(x_garbage, available=available[None, :]) == pytest.approx(expected)
    # excluded values never leak into the score
    x_other = x.copy()
    x_other[~available] = 0.0
    assert score(x_other, available=available[None, :]) == pytest.approx(expected)


def test_renormalisation_keeps_constant_scores_constant():
    available = _public_only_availability()
    assert score([0.6] * 12, available=available[None, :]) == pytest.approx(60.0)


def test_neutral_strategy_assigns_half():
    available = _public_only_availability()
    x = np.array(A, dtype=float)
    x_neutral = x.copy()
    x_neutral[~available] = 0.5
    assert score(x, available=available[None, :], strategy="neutral") == pytest.approx(score(x_neutral))


def test_penalties_are_multiplicative():
    assert scoring.penalty_factor([0.3, 0.4])[0] == pytest.approx(0.7 * 0.6)
    assert scoring.penalty_factor(np.array([[0.0, 0.0], [0.3, 0.0]])) == pytest.approx([1.0, 0.7])


def test_scores_stay_in_range():
    rng = np.random.default_rng(0)
    x = rng.uniform(-0.5, 1.5, size=(500, 12))
    available = rng.uniform(size=(500, 12)) > 0.3
    available[:, KEYS.index("vie_di_fuga")] = True
    for band in CFG["timebands"]["bands"]:
        s = scoring.segment_scores(x, available, band, "donna+over75")
        assert np.all((s >= 0) & (s <= 100))
        assert not np.isnan(s).any()


def test_color_classes():
    assert list(scoring.color_class([39.9, 40.0, 65.0, 65.1])) == ["rossa", "gialla", "gialla", "verde"]


# --------------------------------------------------------------------------- #
# Reliability
# --------------------------------------------------------------------------- #
def test_reliability_all_measured_is_one():
    flags = np.array([["measured"] * 12])
    for band in CFG["timebands"]["bands"]:
        assert scoring.reliability(flags, band)[0] == pytest.approx(1.0)


def test_reliability_public_data_only():
    flags = ["measured"] * 12
    for key in ("episodi", "cura", "folla"):
        flags[KEYS.index(key)] = "excluded"
    for key in ("persone", "visuale"):
        flags[KEYS.index(key)] = "proxy"
    flags = np.array([flags])
    # night: 1 - (8 + 7 + 4)/100 - 0.5 * (14 + 10)/100
    assert scoring.reliability(flags, "sera")[0] == pytest.approx(0.69)
    # day: 1 - (12 + 12 + 6)/100 - 0.5 * (12 + 10)/100
    assert scoring.reliability(flags, "giorno")[0] == pytest.approx(0.59)


def test_worst_parameters_rank_by_points_lost():
    available = _public_only_availability()
    worst = scoring.worst_parameters(np.array([C]), available[None, :], "sera")[0]
    assert len(worst) == 3
    assert worst[0] == "persone"  # 14 points of weight at 0.2
    assert not set(worst) & {"episodi", "cura", "folla"}


# --------------------------------------------------------------------------- #
# Darkness penalty (team decision, 16/10/2026)
# --------------------------------------------------------------------------- #
def test_dark_penalty_is_zero_by_day_and_grows_with_darkness():
    light = np.array([1.0, 0.5, 0.0, np.nan])
    assert scoring.dark_penalty(light, "giorno").tolist() == [0.0, 0.0, 0.0, 0.0]
    p = scoring.dark_penalty(light, "sera")
    assert p[0] == pytest.approx(0.05) and p[2] == pytest.approx(0.25)
    assert p[0] < p[1] < p[2] and p[3] == pytest.approx(p[1])       # unknown light counts as 0.5
    assert scoring.dark_penalty(light, "prima_ora_buio") == pytest.approx(p / 2)


def test_dark_penalty_by_profile():
    light = np.array([0.0, 1.0])
    ref = scoring.dark_penalty(light, "sera", "riferimento")
    assert scoring.dark_penalty(light, "sera", "donna") == pytest.approx(2 * ref)
    assert scoring.dark_penalty(light, "sera", "in_compagnia") == pytest.approx(0.5 * ref)
    assert scoring.dark_penalty(np.array([0.0]), "sera", "donna+over75")[0] <= CFG["scoring"]["penalties"]["dark"]["max"]


def test_dark_penalty_keeps_women_score_below_reference_on_poor_light():
    """With the darkness penalty the coherence check of section 10 holds on typical poorly lit segments."""
    rng = np.random.default_rng(3)
    x = rng.uniform(0, 1, size=(2000, 12))
    x[:, KEYS.index("luce")] = rng.uniform(0, 0.5, size=2000)
    available = np.ones_like(x, dtype=bool)
    for key in ("episodi", "cura", "folla"):
        available[:, KEYS.index(key)] = False
    s = {}
    for prof in ("riferimento", "donna"):
        dark = scoring.dark_penalty(x[:, KEYS.index("luce")], "sera", prof)
        s[prof] = scoring.segment_scores(x, available, "sera", prof, 1.0 - dark)
    assert (s["donna"] <= s["riferimento"] + 1e-9).all()
