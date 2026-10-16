"""The browser core (frontend/src/core.js) agrees with the Python model.

Runs core.js in Node on the payload of the generated app (frontend/lumi.html)
and compares time bands, sun times and least-cost routes with model/timebands.py
and model/routing.py. Skipped when Node or the generated page is missing.
"""

import json
import re
import shutil
import subprocess
from datetime import datetime, timedelta

import numpy as np
import pytest

from model import routing, timebands
from model.config import ROOT, load_config

CORE = ROOT / "frontend" / "src" / "core.js"
PAGE = ROOT / "frontend" / "lumi.html"

pytestmark = pytest.mark.skipif(shutil.which("node") is None or not PAGE.exists(),
                                reason="servono Node.js e frontend/lumi.html (python -m pipeline.frontend)")

RUNNER = r"""
const QV = require(process.argv[2]);
const fs = require("fs");
const DATA = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));
const job = JSON.parse(fs.readFileSync(process.argv[4], "utf8"));
(async () => {
  const ctx = await QV.load(DATA), G = QV.graph(ctx), out = { moments: [], routes: [] };
  for (const iso of job.moments) {
    const m = QV.moment(DATA.model, new Date(iso));
    out.moments.push({ band: m.band, day: m.day, sunrise: m.sunrise, sunset: m.sunset });
  }
  const st = QV.scores(ctx, { band: "sera", day: "feriale", hour: 20, rain: false, profiles: ["donna"] });
  out.S = Array.from(st.S); out.len = Array.from(G.len); out.u = Array.from(ctx.u); out.v = Array.from(ctx.v); out.lam = st.lam;
  for (const [i, j] of job.pairs) {
    const r = QV.route(ctx, G, st, { i, t: 0 }, { i: j, t: 1 }, st.lam);
    out.routes.push(r ? { cost: r.cost, length: r.length } : null);
  }
  process.stdout.write(JSON.stringify(out));
})();
"""


@pytest.fixture(scope="module")
def js(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("js")
    html = PAGE.read_text(encoding="utf-8")
    data = re.search(r"const DATA = (\{.*?\});\nconst IMG", html, re.S).group(1)
    (tmp / "data.json").write_text(data, encoding="utf-8")
    n = json.loads(data)["n"]
    rng = np.random.default_rng(7)
    start = datetime(2026, 1, 3, 0, 20)
    moments = [(start + timedelta(minutes=int(m))) for m in rng.integers(0, 365 * 24 * 60, 120)]
    pairs = rng.integers(0, n, size=(25, 2)).tolist()
    job = {"moments": [timebands.localize(m).isoformat() for m in moments], "pairs": pairs}
    (tmp / "job.json").write_text(json.dumps(job), encoding="utf-8")
    (tmp / "run.js").write_text(RUNNER, encoding="utf-8")
    res = subprocess.run(["node", str(tmp / "run.js"), str(CORE), str(tmp / "data.json"), str(tmp / "job.json")],
                         capture_output=True, text=True, timeout=120, check=True)
    return moments, pairs, json.loads(res.stdout)


def test_bands_and_day_types_match_python(js):
    cfg = load_config()
    moments, _, out = js
    for when, m in zip(moments, out["moments"]):
        assert m["band"] == timebands.band_at(when, cfg), when
        assert m["day"] == timebands.day_type(when, cfg), when


def test_sun_times_within_three_minutes_of_astral(js):
    cfg = load_config()
    moments, _, out = js
    for when, m in zip(moments, out["moments"]):
        rise, sset = timebands.sun_times(timebands.localize(when, cfg).date(), cfg)
        assert abs(m["sunrise"] - (rise.hour * 60 + rise.minute + rise.second / 60)) < 3, when
        assert abs(m["sunset"] - (sset.hour * 60 + sset.minute + sset.second / 60)) < 3, when


def test_routes_match_python_dijkstra(js):
    cfg = load_config()
    _, pairs, out = js
    u, v = np.array(out["u"]), np.array(out["v"])
    length, score = np.array(out["len"]), np.array(out["S"], dtype=float)
    adj = routing.build_graph(u, v)
    found = 0
    for (i, j), r in zip(pairs, out["routes"]):
        py = routing.least_cost_route(u, v, length, score, int(u[i]), int(v[j]), out["lam"], cfg=cfg, adj=adj)
        if py is None:
            assert r is None
            continue
        found += 1
        # JS starts at the beginning of segment i (node u) and ends at the end of segment j (node v)
        assert r["cost"] == pytest.approx(py.cost, rel=1e-4, abs=1e-6)
        assert r["length"] == pytest.approx(py.length_m, rel=1e-3, abs=0.5)
    assert found >= 20
