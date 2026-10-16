"""Scores for any date, time, profile and weather, with optional demo events.

    python -m pipeline.scenario --datetime 2026-11-20T21:30 --profilo donna --meteo pioggia
    python -m pipeline.scenario --datetime 2026-11-18T21:00 --demo      # adds the simulated demo events

Writes ``exports/scenario_<data>_<ora>_<profilo>[_meteo][_demo].geojson`` and prints
a summary. The API (phase 4) will reuse ``compute_at``.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from model import dynamic, scoring, timebands
from model.config import load_config, param_keys
from pipeline import osm, params
from pipeline.common import EXPORTS, PROCESSED, log, setup_logging


class Engine:
    """Static context built once (about 15 s), then any datetime is cheap."""

    def __init__(self, cfg: dict[str, Any] | None = None):
        self.cfg = cfg or load_config()
        segments = gpd.read_parquet(PROCESSED / "segments.parquet")
        self.ctx = params.Context(segments, osm.load_features(), self.cfg)
        self.static = params.static_parameters(self.ctx)
        meta = json.loads(params.PARAMS_META.read_text(encoding="utf-8")) if params.PARAMS_META.exists() else {}
        self.people_norm = float(meta.get("people_norm") or 1.0)

    def compute_at(self, when: datetime, profile: str = "riferimento", meteo: str | None = None,
                   demo: bool = False) -> tuple[pd.DataFrame, dict[str, Any]]:
        cfg = self.cfg
        when = timebands.localize(when, cfg)
        band = timebands.band_at(when, cfg)
        res = params.band_parameters(self.ctx, band, when, self.static)
        keys = param_keys(cfg)
        X, F = res["X"], res["F"]
        jp = keys.index("persone")
        X[:, jp] = np.minimum(1.0, X[:, jp] / self.people_norm)
        weather = dynamic.weather_at(when, meteo, cfg)
        X = dynamic.apply_weather(X, weather["condizione"], cfg)
        events = dynamic.active_events(dynamic.load_events(demo, cfg), when, cfg)
        X, near_event = dynamic.apply_events(X, self.ctx.lines, events, cfg)
        X = np.where(F == scoring.EXCLUDED, np.nan, X)
        dark = scoring.dark_penalty(X[:, keys.index("luce")], band, profile, cfg)
        penalty = scoring.penalty_factor(np.column_stack([res["pen_bloccante"], res["pen_parco_buio"], dark]))
        S = scoring.segment_scores(X, F != scoring.EXCLUDED, band, profile, penalty, cfg=cfg)
        lam = scoring.profile_lambda(profile, cfg)
        out = pd.DataFrame({
            "segment_id": self.ctx.seg["segment_id"].to_numpy(),
            "S": np.round(S, 2),
            "classe_colore": scoring.color_class(S, cfg),
            "affidabilita": np.round(scoring.reliability(F, band, cfg), 4),
            "costo_per_m": np.round(scoring.path_cost(1.0, S, lam), 4),
            "vicino_a_evento": near_event,
        })
        info = {
            "datetime": when.isoformat(), "fascia": band, "tipo_giorno": res["day_type"],
            "profilo": scoring.profile_key(profile, cfg), "lambda": lam, "meteo": weather,
            "eventi_attivi": events["titolo"].tolist() if len(events) else [],
            "scenario_demo": bool(demo and len(events) and events["simulato"].any()),
            "S_medio": round(float(np.nanmean(S)), 1), "pct_rossi": round(100 * float((S < cfg["scoring"]["classes"]["red_below"]).mean()), 1),
        }
        return out, info


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Punteggio per data, ora, profilo e meteo")
    parser.add_argument("--datetime", required=True, help="es. 2026-11-20T21:30 (ora locale)")
    parser.add_argument("--profilo", default="riferimento", help="es. donna oppure donna+giovani_16_34")
    parser.add_argument("--meteo", choices=list(dynamic.CONDITIONS), help="forza il meteo (altrimenti Open-Meteo)")
    parser.add_argument("--demo", action="store_true", help="usa anche gli eventi simulati di data/demo/")
    args = parser.parse_args(argv)
    setup_logging()
    engine = Engine()
    when = datetime.fromisoformat(args.datetime)
    scores, info = engine.compute_at(when, args.profilo, args.meteo, args.demo)
    segments = gpd.read_parquet(PROCESSED / "segments.parquet")[["segment_id", "via", "quartiere", "classe", "geometry"]]
    gdf = segments.merge(scores, on="segment_id")
    gdf["colore"] = gdf["classe_colore"].map(engine.cfg["scoring"]["classes"]["colors"])
    gdf["scenario_demo"] = info["scenario_demo"]
    name = f"scenario_{when:%Y%m%d_%H%M}_{info['profilo']}"
    name += f"_{args.meteo}" if args.meteo else ""
    name += "_demo" if args.demo else ""
    EXPORTS.mkdir(parents=True, exist_ok=True)
    (EXPORTS / f"{name}.geojson").write_text(gdf.to_json(drop_id=True, to_wgs84=True, ensure_ascii=False), encoding="utf-8")
    log.info("scenario salvato in exports/%s.geojson", name)
    print(json.dumps(info, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
