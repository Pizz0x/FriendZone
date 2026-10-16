"""Run the whole pipeline in order. Idempotent: downloads are cached on disk.

    python -m pipeline.run_all                # everything, reusing cached downloads
    python -m pipeline.run_all --force        # download OSM again
    python -m pipeline.run_all --planet       # allow the AWS planet extract if Overpass is down
    python -m pipeline.run_all --until segments
"""

from __future__ import annotations

import argparse
import time

from model.config import load_config
from pipeline import aggregate, osm, params, segments, sources_public, validate
from pipeline.common import REPORTS, ensure_dirs, log, setup_logging

STEPS = ["sources", "osm", "segments", "params", "aggregate", "validate"]


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Pipeline Quartieri Vivi")
    parser.add_argument("--force", action="store_true", help="riscarica i dati OSM anche se in cache")
    parser.add_argument("--planet", action="store_true", help="se Overpass non risponde, estrai Vicenza dal planet OSM su AWS")
    parser.add_argument("--until", choices=STEPS, default=STEPS[-1], help="ultimo passo da eseguire")
    parser.add_argument("--skip-probe", action="store_true", help="non verificare la raggiungibilità delle fonti")
    args = parser.parse_args(argv)

    setup_logging()
    ensure_dirs()
    cfg = load_config()
    t0 = time.time()
    last = STEPS.index(args.until)

    if not args.skip_probe:
        log.info("== verifica delle fonti pubbliche")
        sources_public.probe_all(cfg)
    if last < 1:
        return

    log.info("== OpenStreetMap")
    meta = osm.acquire(cfg, force=args.force, allow_planet=args.planet)
    if last < 2:
        return

    log.info("== tratti e quartieri")
    segs = segments.run(cfg)
    quartieri = segments.load_quartieri()
    boundary = osm.load_boundary().geometry.iloc[0]
    cov = validate.osm_coverage(segs, osm.load_features(), boundary, cfg)
    (REPORTS / "osm_coverage.md").write_text(validate.coverage_markdown(cov, meta), encoding="utf-8")
    if last < 3:
        validate.phase1_map(segs, quartieri, boundary, REPORTS / "check_map.html")
        return

    log.info("== parametri per fascia")
    params.run(cfg)
    if last < 4:
        return

    log.info("== punteggi, aggregati ed export")
    aggregate.run(cfg)
    if last < 5:
        return

    log.info("== validazione e mappa di controllo")
    validate.run(cfg)
    log.info("pipeline completata in %.0f s", time.time() - t0)


if __name__ == "__main__":
    main()
