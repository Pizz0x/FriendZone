"""Build the pitch deck ``frontend/presentazione.html`` from ``frontend/src/presentazione.html``.

The deck is one self-contained page (keyboard-driven slides with motion, no
audio). It shows the real streets of Vicenza coloured by their evening score
for the profile "donna", drawn from Piazza dei Signori outwards, so the page
inlines that geometry as SVG paths and the logo as a data URI.

    python -m pipeline.pitch            # needs exports/segments_sera_donna.geojson (python -m pipeline.run_all)
"""

from __future__ import annotations

import base64
import json
import math

from model.config import ROOT
from pipeline.common import log, setup_logging

FRONTEND = ROOT / "frontend"
SRC = FRONTEND / "src" / "presentazione.html"
OUT = FRONTEND / "presentazione.html"
SEGMENTS = ROOT / "exports" / "segments_sera_donna.geojson"
MARK = FRONTEND / "assets" / "brand" / "mark.webp"

LAT0, LON0 = 45.5470, 11.5465       # near Piazza dei Signori: centre of the drawing
W, H = 1920, 1080                   # SVG user units, as the slides
METRES_PER_UNIT = 2.0
MARGIN = 60                         # keep segments that start just off-canvas
TOLERANCE = 0.8                     # Douglas-Peucker tolerance, in user units


def _project(lon: float, lat: float) -> tuple[float, float]:
    kx = math.cos(math.radians(LAT0)) * 111320 / METRES_PER_UNIT
    ky = 110540 / METRES_PER_UNIT
    return W / 2 + (lon - LON0) * kx, H / 2 - (lat - LAT0) * ky


def _simplify(pts: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    if len(pts) < 3:
        return pts
    (x1, y1), (x2, y2) = pts[0], pts[-1]
    dx, dy = x2 - x1, y2 - y1
    norm = math.hypot(dx, dy) or 1e-9
    k, dmax = 0, -1.0
    for i in range(1, len(pts) - 1):
        d = abs(dy * pts[i][0] - dx * pts[i][1] + x2 * y1 - y2 * x1) / norm
        if d > dmax:
            k, dmax = i, d
    if dmax <= tol:
        return [pts[0], pts[-1]]
    return _simplify(pts[:k + 1], tol)[:-1] + _simplify(pts[k:], tol)


def street_paths(path=SEGMENTS) -> dict[str, str]:
    """SVG path data: every street in view, then one path per colour class, nearest to the centre first."""
    segs = []
    for f in json.loads(path.read_text(encoding="utf-8"))["features"]:
        geo = f["geometry"]
        for line in [geo["coordinates"]] if geo["type"] == "LineString" else geo["coordinates"]:
            pts = [_project(*c) for c in line]
            if not any(-MARGIN < x < W + MARGIN and -MARGIN < y < H + MARGIN for x, y in pts):
                continue
            pts = _simplify(pts, TOLERANCE)
            cx, cy = sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)
            segs.append((math.hypot(cx - W / 2, cy - H / 2), f["properties"]["classe_colore"], pts))
    segs.sort(key=lambda s: s[0])

    def d(items) -> str:
        return "".join("M" + " ".join(f"{round(x)} {round(y)}" for x, y in pts) for _, _, pts in items)

    return {"all": d(segs), "verde": d([s for s in segs if s[1] == "verde"]),
            "gialla": d([s for s in segs if s[1] == "gialla"]), "rossa": d([s for s in segs if s[1] == "rossa"])}


def render() -> str:
    paths = street_paths()
    mark = "data:image/webp;base64," + base64.b64encode(MARK.read_bytes()).decode("ascii")
    return (SRC.read_text(encoding="utf-8")
            .replace("__M_ALL__", paths["all"]).replace("__M_V__", paths["verde"])
            .replace("__M_G__", paths["gialla"]).replace("__M_R__", paths["rossa"])
            .replace("__MARK__", mark))


def artifact(html: str) -> str:
    """The same page for an artifact host, which adds doctype, html, head and body itself."""
    head = html[html.index("<head>") + 6:html.index("</head>")]
    head = "\n".join(line for line in head.splitlines() if not line.lstrip().startswith("<meta"))
    return head.strip() + "\n" + html[html.index("<body>") + 6:html.index("</body>")].strip() + "\n"


def main() -> None:
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Genera la presentazione frontend/presentazione.html")
    parser.add_argument("--artifact", help="scrive anche la versione senza <html>/<head>/<body> in questo file")
    args = parser.parse_args()
    setup_logging()
    html = render()
    OUT.write_text(html, encoding="utf-8")
    log.info("presentazione scritta in %s (%.2f MB)", OUT, OUT.stat().st_size / 1e6)
    if args.artifact:
        Path(args.artifact).write_text(artifact(html), encoding="utf-8")


if __name__ == "__main__":
    main()
