"""Coverage reports, validation report and the folium check map."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import folium
from branca.element import MacroElement
from jinja2 import Template
import geopandas as gpd
import numpy as np
import pandas as pd

from model.config import load_config
from pipeline.common import PROCESSED, REPORTS, log

COVERAGE_JSON = PROCESSED / "coverage_osm.json"
POI_AMENITIES_DEFAULT = ["bar", "cafe", "restaurant", "pub", "fast_food", "ice_cream", "pharmacy", "cinema",
                         "theatre", "library", "police", "hospital", "clinic", "nightclub"]
VEHICLE_CLASSES = {"trunk", "primary", "secondary", "tertiary", "unclassified", "residential", "service", "living_street"}


def _pct(part: float, whole: float) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0


# --------------------------------------------------------------------------- #
# OSM coverage (phase 1)
# --------------------------------------------------------------------------- #
def osm_coverage(segments: gpd.GeoDataFrame, feats: gpd.GeoDataFrame, boundary, cfg: dict[str, Any]) -> dict[str, Any]:
    in_area = feats[feats.intersects(boundary)]
    length = segments["lunghezza_m"]
    total_len = float(length.sum())

    def seg_share(mask: pd.Series) -> dict[str, float]:
        return {"tratti_pct": _pct(mask.sum(), len(segments)), "lunghezza_pct": _pct(length[mask].sum(), total_len)}

    lit = segments["tag_lit"].notna()
    lit_yes = segments["tag_lit"].fillna("").str.contains("yes|24/7|automatic|sunset|dusk|limited|interval")
    lit_no = segments["tag_lit"].fillna("").str.contains("no|disused") & ~lit_yes
    sidewalk_cols = [c for c in segments.columns if c.startswith("tag_sidewalk")]
    has_sidewalk = segments[sidewalk_cols].notna().any(axis=1)
    is_vehicle = segments["classe"].isin(VEHICLE_CLASSES)
    is_sidewalk_way = segments["tag_footway"].fillna("").str.contains("sidewalk")
    amenities = cfg["pois"].get("amenities", POI_AMENITIES_DEFAULT)
    poi = in_area[in_area.get("shop").notna() | in_area.get("amenity").isin(amenities)]
    poi = poi.drop_duplicates(subset=["element", "osmid"])
    lamps = in_area[(in_area.get("highway") == "street_lamp") & (in_area.geom_type == "Point")]
    stops = in_area[(in_area.get("highway") == "bus_stop") | (in_area.get("public_transport") == "platform")
                    | in_area.get("railway").isin(["station", "halt"])]
    stops_pts = stops[stops.geom_type == "Point"]
    benches = in_area[in_area.get("amenity") == "bench"]
    barriers = in_area[in_area.get("barrier").isin(["wall", "hedge", "fence", "retaining_wall", "city_wall"])
                       & in_area.geom_type.isin(["LineString", "MultiLineString"])]
    landuse = in_area[in_area.get("landuse").notna() & in_area.geom_type.isin(["Polygon", "MultiPolygon"])]
    metric = cfg["area"]["crs_metric"]
    area_m2 = gpd.GeoSeries([boundary], crs="EPSG:4326").to_crs(metric).area.iloc[0]
    landuse_cover = landuse.to_crs(metric).union_all().intersection(
        gpd.GeoSeries([boundary], crs="EPSG:4326").to_crs(metric).iloc[0]).area if len(landuse) else 0.0
    classes = segments.groupby("classe")["lunghezza_m"].agg(["count", "sum"]).sort_values("sum", ascending=False)

    cov = {
        "tratti": int(len(segments)),
        "lunghezza_km": round(total_len / 1000, 1),
        "superficie_comune_km2": round(area_m2 / 1e6, 2),
        "lit": {"con_tag": seg_share(lit), "lit_si": seg_share(lit_yes), "lit_no": seg_share(lit_no)},
        "lampioni_osm": int(len(lamps)),
        "poi": {"totale": int(len(poi)),
                "con_opening_hours": int(poi["opening_hours"].notna().sum()) if "opening_hours" in poi else 0,
                "con_opening_hours_pct": _pct(poi["opening_hours"].notna().sum(), len(poi)) if "opening_hours" in poi else 0.0,
                "negozi": int(poi["shop"].notna().sum()),
                "per_amenity": {k: int(v) for k, v in poi["amenity"].value_counts().items()}},
        "sidewalk": {"tratti_con_tag_sidewalk": seg_share(has_sidewalk),
                     "strade_veicolari_con_tag_sidewalk": {
                         "tratti_pct": _pct((has_sidewalk & is_vehicle).sum(), is_vehicle.sum()),
                         "lunghezza_pct": _pct(length[has_sidewalk & is_vehicle].sum(), length[is_vehicle].sum())},
                     "marciapiedi_mappati_a_parte": seg_share(is_sidewalk_way)},
        "surface": seg_share(segments["tag_surface"].notna()),
        "fermate": int(len(stops_pts)),
        "fermate_con_shelter": int(stops_pts["shelter"].notna().sum()) if "shelter" in stops_pts else 0,
        "panchine": int(len(benches)),
        "barriere_lineari_km": round(barriers.to_crs(metric).length.sum() / 1000, 1),
        "landuse_copertura_pct": _pct(landuse_cover, area_m2),
        "tunnel_tratti": int(segments["tag_tunnel"].notna().sum()),
        "covered_tratti": int(segments["tag_covered"].notna().sum()),
        "vicoli_ciechi": int(segments["vicolo_cieco"].sum()),
        "classi": {k: {"tratti": int(r["count"]), "km": round(r["sum"] / 1000, 1)} for k, r in classes.iterrows()},
    }
    PROCESSED.mkdir(parents=True, exist_ok=True)
    COVERAGE_JSON.write_text(json.dumps(cov, indent=2, ensure_ascii=False), encoding="utf-8")
    return cov


def coverage_markdown(cov: dict[str, Any], meta: dict[str, Any]) -> str:
    lines = [
        "# Copertura dei dati OpenStreetMap — Comune di Vicenza",
        "",
        f"Fonte: {meta.get('source')} (metodo `{meta.get('method')}`), dati OSM aggiornati al "
        f"{meta.get('osm_timestamp')}, estratti il {meta.get('downloaded_at')}.",
        "",
        "Più bassa è la copertura di un tag, più i parametri che lo usano saranno `proxy` o `excluded`.",
        "",
        "| Indicatore | Valore |",
        "|---|---|",
        f"| Tratti pedonali | {cov['tratti']:,} ({cov['lunghezza_km']} km) |",
        f"| Tratti con tag `lit` | {cov['lit']['con_tag']['tratti_pct']}% dei tratti, {cov['lit']['con_tag']['lunghezza_pct']}% della lunghezza |",
        f"| … di cui illuminati (`lit=yes` e simili) | {cov['lit']['lit_si']['lunghezza_pct']}% della lunghezza |",
        f"| … di cui non illuminati (`lit=no`) | {cov['lit']['lit_no']['lunghezza_pct']}% della lunghezza |",
        f"| Lampioni (`highway=street_lamp`) | {cov['lampioni_osm']:,} |",
        f"| Attività (negozi + amenity del brief) | {cov['poi']['totale']:,} |",
        f"| … con `opening_hours` | {cov['poi']['con_opening_hours']:,} ({cov['poi']['con_opening_hours_pct']}%) |",
        f"| Tratti con tag `sidewalk*` | {cov['sidewalk']['tratti_con_tag_sidewalk']['tratti_pct']}% dei tratti |",
        f"| Strade veicolari con tag `sidewalk*` | {cov['sidewalk']['strade_veicolari_con_tag_sidewalk']['lunghezza_pct']}% della lunghezza |",
        f"| Marciapiedi mappati come vie separate (`footway=sidewalk`) | {cov['sidewalk']['marciapiedi_mappati_a_parte']['lunghezza_pct']}% della lunghezza |",
        f"| Tratti con `surface` | {cov['surface']['lunghezza_pct']}% della lunghezza |",
        f"| Fermate e stazioni | {cov['fermate']:,} (con `shelter`: {cov['fermate_con_shelter']:,}) |",
        f"| Panchine | {cov['panchine']:,} |",
        f"| Muri, siepi, recinzioni (linee) | {cov['barriere_lineari_km']} km |",
        f"| Superficie comunale coperta da `landuse` | {cov['landuse_copertura_pct']}% |",
        f"| Tratti in tunnel / coperti | {cov['tunnel_tratti']} / {cov['covered_tratti']} |",
        f"| Tratti in vicolo cieco | {cov['vicoli_ciechi']:,} |",
        "",
        "## Tratti per classe stradale",
        "",
        "| Classe | Tratti | km |",
        "|---|---:|---:|",
    ]
    lines += [f"| {k} | {v['tratti']:,} | {v['km']} |" for k, v in cov["classi"].items()]
    lines += ["", "## Attività per tipo (amenity)", "", "| amenity | n |", "|---|---:|"]
    lines += [f"| {k} | {v} |" for k, v in cov["poi"]["per_amenity"].items()]
    lines.append(f"| negozi (`shop=*`) | {cov['poi']['negozi']} |")
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------- #
# Check map
# --------------------------------------------------------------------------- #
def _geojson_lines(gdf: gpd.GeoDataFrame, props: list[str], tolerance_m: float = 1.0) -> dict:
    """Compact GeoJSON: light simplification and 5-decimal coordinates."""
    metric = load_config()["area"]["crs_metric"]
    g = gdf.to_crs(metric).geometry.simplify(tolerance_m).to_crs("EPSG:4326")
    feats = []
    for i, (geom, row) in enumerate(zip(g, gdf[props].itertuples(index=False))):
        coords = [[round(x, 5), round(y, 5)] for x, y in geom.coords] if geom.geom_type == "LineString" else \
            [[[round(x, 5), round(y, 5)] for x, y in part.coords] for part in geom.geoms]
        gtype = "LineString" if geom.geom_type == "LineString" else "MultiLineString"
        properties = {"i": i}
        for k, v in zip(props, row):
            properties[k] = None if (v is None or (isinstance(v, float) and np.isnan(v))) else (
                round(float(v), 1) if isinstance(v, (float, np.floating)) else v)
        feats.append({"type": "Feature", "geometry": {"type": gtype, "coordinates": coords}, "properties": properties})
    return {"type": "FeatureCollection", "features": feats}


class _MapScript(MacroElement):
    """Inline JavaScript rendered after the map object exists."""

    _template = Template("{% macro script(this, kwargs) %}{{ this.code }}{% endmacro %}")

    def __init__(self, code: str):
        super().__init__()
        self._name = "MapScript"
        self.code = code


def _base_map(boundary) -> folium.Map:
    c = boundary.centroid
    m = folium.Map(location=[c.y, c.x], zoom_start=13, tiles="OpenStreetMap", control_scale=True, prefer_canvas=True)
    folium.GeoJson(boundary.__geo_interface__, name="Confine comunale",
                   style_function=lambda _: {"color": "#333", "weight": 2, "fill": False, "dashArray": "4"}).add_to(m)
    return m


CLASS_COLORS = {
    "pedonale": "#1a9850", "residenziale": "#91cf60", "principale": "#d73027", "servizio": "#999999",
    "sentiero": "#8c510a", "scale": "#762a83", "altro": "#4575b4",
}


def _class_group(c: str) -> str:
    if c in {"pedestrian", "footway", "living_street"}:
        return "pedonale"
    if c in {"residential", "unclassified"}:
        return "residenziale"
    if c in {"trunk", "primary", "secondary", "tertiary"}:
        return "principale"
    if c == "service":
        return "servizio"
    if c in {"path", "track", "bridleway", "cycleway"}:
        return "sentiero"
    if c == "steps":
        return "scale"
    return "altro"


def phase1_map(segments: gpd.GeoDataFrame, quartieri: gpd.GeoDataFrame, boundary, out: Path) -> Path:
    """First check map: segments by road class, neighbourhood outlines."""
    seg = segments.assign(gruppo=segments["classe"].map(_class_group))
    m = _base_map(boundary)
    folium.GeoJson(
        quartieri.__geo_interface__, name="Quartieri",
        style_function=lambda _: {"color": "#555", "weight": 1, "fillOpacity": 0.03},
        tooltip=folium.GeoJsonTooltip(fields=["quartiere", "fonte_quartiere"], aliases=["Quartiere", "Fonte"]),
    ).add_to(m)
    data = _geojson_lines(seg, ["via", "classe", "gruppo", "quartiere", "lunghezza_m"])
    js = f"""
    var segData = {json.dumps(data, separators=(',', ':'))};
    var classColors = {json.dumps(CLASS_COLORS)};
    var segLayer = L.geoJSON(segData, {{
        style: function(f) {{ return {{color: classColors[f.properties.gruppo] || '#4575b4', weight: 2, opacity: 0.85}}; }},
        onEachFeature: function(f, layer) {{
            var p = f.properties;
            layer.bindTooltip('<b>' + p.via + '</b><br>classe: ' + p.classe + '<br>quartiere: ' + p.quartiere +
                              '<br>lunghezza: ' + p.lunghezza_m + ' m', {{sticky: true}});
        }}
    }}).addTo({m.get_name()});
    var legend = L.control({{position: 'bottomright'}});
    legend.onAdd = function() {{
        var d = L.DomUtil.create('div', 'legend');
        d.style.cssText = 'background:white;padding:6px 8px;font:12px sans-serif;border-radius:4px';
        d.innerHTML = '<b>Classe del tratto</b><br>' + Object.keys(classColors).map(function(k) {{
            return '<span style="display:inline-block;width:18px;height:3px;background:' + classColors[k] +
                   ';vertical-align:middle;margin-right:4px"></span>' + k; }}).join('<br>');
        return d;
    }};
    legend.addTo({m.get_name()});
    """
    _MapScript(js).add_to(m)
    folium.LayerControl().add_to(m)
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    log.info("mappa di controllo (fase 1): %s", out)
    return out


# --------------------------------------------------------------------------- #
# Phase 2: validation report and score map
# --------------------------------------------------------------------------- #
DISCLAIMER = ("*Il punteggio stima la sicurezza percepita a partire dai dati disponibili. "
              "Non misura la sicurezza reale di un luogo.*")


def _md_table(df: pd.DataFrame, floatfmt: str = "{:.1f}") -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for row in df.itertuples(index=False):
        cells = []
        for v in row:
            if isinstance(v, (float, np.floating)):
                cells.append("" if np.isnan(v) else floatfmt.format(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def coherence_checks(segments: gpd.GeoDataFrame, params: pd.DataFrame, scores: pd.DataFrame,
                     cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Consistency checks of section 10 of the brief, each PASS or FAIL with a reason."""
    from model import scoring
    from pipeline import aggregate, pois
    from pipeline import osm as osm_mod
    from pipeline.params import matrices

    checks: list[dict[str, Any]] = []
    keys = [p["key"] for p in cfg["parameters"]]
    seg = segments.set_index("segment_id")

    # 1. evening: pedestrian streets of the historic centre above industrial areas
    sera = scores[(scores["fascia"] == "sera") & (scores["profilo"] == "riferimento")].set_index("segment_id")
    feats = osm_mod.load_features().to_crs(cfg["area"]["crs_metric"])
    landuse = pois.landuse_polygons(feats, cfg)
    seg_m = segments.to_crs(cfg["area"]["crs_metric"])
    mids = gpd.GeoDataFrame({"segment_id": seg_m["segment_id"]},
                            geometry=seg_m.geometry.interpolate(0.5, normalized=True), crs=seg_m.crs)
    centro = _historic_centre(feats, cfg)
    if centro is not None:
        in_centre = mids[mids.within(centro)]["segment_id"]
        ped_centre = [s for s in in_centre if seg.at[s, "classe"] in {"pedestrian", "footway", "living_street"}]
    else:
        ped_centre = []
    industrial = landuse[landuse["classe_suolo"] == "industrial"]
    in_ind = gpd.sjoin(mids, industrial[["geometry"]], predicate="within")["segment_id"].unique()
    if len(ped_centre) >= 10 and len(in_ind) >= 10:
        s_c = aggregate._weighted(sera.loc[ped_centre, "S"], seg.loc[ped_centre, "lunghezza_m"])
        s_i = aggregate._weighted(sera.loc[in_ind, "S"], seg.loc[in_ind, "lunghezza_m"])
        checks.append({"controllo": "Di sera le vie pedonali del centro storico hanno S medio più alto delle zone industriali",
                       "esito": "PASS" if s_c > s_i else "FAIL",
                       "dettaglio": f"vie pedonali del centro storico ({CENTRE_DESCRIPTION}): S = {s_c:.1f} su {len(ped_centre)} "
                                    f"tratti; tratti in aree `landuse=industrial`: S = {s_i:.1f} su {len(in_ind)} tratti"})
    else:
        checks.append({"controllo": "Di sera le vie pedonali del centro storico hanno S medio più alto delle zone industriali",
                       "esito": "FAIL", "dettaglio": f"campione insufficiente: {len(ped_centre)} tratti in centro, {len(in_ind)} in zone industriali"})

    # 2. underpasses are penalised
    band_rows = params[params["fascia"] == "sera"].set_index("segment_id")
    under = band_rows[band_rows["pen_bloccante"] > 0]
    if len(under):
        others = sera.drop(index=under.index, errors="ignore")
        s_u, s_o = sera.loc[under.index, "S"].mean(), others["S"].mean()
        ok = bool((under["fattore_penalita"] <= 1 - cfg["scoring"]["penalties"]["blocking"] + 1e-9).all()) and s_u < s_o
        pen = json.loads((PROCESSED / "params_meta.json").read_text(encoding="utf-8"))["penalita"]
        checks.append({"controllo": "I sottopassi (e i passaggi coperti o senza uscita) risultano penalizzati",
                       "esito": "PASS" if ok else "FAIL",
                       "dettaglio": f"{len(under):,} tratti con penalità −30% ({pen['sottopassi']} sottopassi, {pen['coperti']} "
                                    f"coperti o passaggi sotto edifici, {pen['passaggi_senza_uscita']} passaggi pedonali senza "
                                    f"uscita): S medio {s_u:.1f} contro {s_o:.1f} degli altri tratti"})
    else:
        checks.append({"controllo": "I sottopassi risultano penalizzati", "esito": "FAIL", "dettaglio": "nessun sottopasso trovato nei dati"})

    # 3. light weighs much less by day
    i = keys.index("luce")
    w_day = scoring.personalized_weights("giorno")[i]
    w_night = scoring.personalized_weights("sera")[i]
    rows_d, X_d, A_d = matrices(params, "giorno", cfg)
    rows_s, X_s, A_s = matrices(params, "sera", cfg)
    def light_effect(X, A, band):
        lo, hi = X.copy(), X.copy()
        lo[:, i], hi[:, i] = 0.0, 1.0
        return (scoring.segment_scores(hi, A, band) - scoring.segment_scores(lo, A, band))[A[:, i]].mean()
    eff_d, eff_s = light_effect(X_d, A_d, "giorno"), light_effect(X_s, A_s, "sera")
    checks.append({"controllo": "Di giorno la luce pesa molto meno",
                   "esito": "PASS" if w_day < 0.25 * w_night and eff_d < 0.25 * eff_s else "FAIL",
                   "dettaglio": f"peso luce giorno {100 * w_day:.1f}% vs sera {100 * w_night:.1f}%; "
                                f"passare da luce 0 a 1 vale in media {eff_d:.1f} punti di giorno e {eff_s:.1f} di sera"})

    # 4. the 'donna' profile never raises S on poorly lit segments
    luce = band_rows["x_luce"]
    poor = luce[(luce < 0.5) & band_rows["flag_luce"].astype(str).ne("excluded")].index
    donna = scores[(scores["fascia"] == "sera") & (scores["profilo"] == "donna")].set_index("segment_id")
    name = "Il profilo «donna» non alza mai S rispetto al riferimento sullo stesso tratto con luce scarsa"
    if len(poor):
        diff = donna.loc[poor, "S"] - sera.loc[poor, "S"]
        n_up = int((diff > 1e-9).sum())
        detail = (f"{len(poor):,} tratti con luce < 0,5 di sera: per il profilo donna S scende in {len(poor) - n_up:,} e "
                  f"sale in {n_up:,} ({100 * n_up / len(poor):.0f}%, al massimo di {diff.max():+.2f} punti); "
                  f"variazione media {diff.mean():+.2f} punti.")
        if n_up:
            rows_e, X_e, A_e = matrices(params, "sera", cfg)
            mask = rows_e["segment_id"].isin(poor).to_numpy()
            s_ref = scoring.segment_scores(X_e, A_e, "sera", "riferimento", rows_e["fattore_penalita"].to_numpy(), cfg=cfg)
            left = {}
            for mult in (2.0, 3.0):
                alt = load_config(fresh=True)
                alt["profiles"]["donna"]["multipliers"]["luce"] = mult
                s_alt = scoring.segment_scores(X_e, A_e, "sera", "donna", rows_e["fattore_penalita"].to_numpy(), cfg=alt)
                left[mult] = int(((s_alt - s_ref)[mask] > 1e-9).sum())
            detail += (" Motivo: è una proprietà del modello, non un errore di calcolo. Il profilo donna aumenta anche i pesi "
                       "di visuale e uso del suolo; dopo la rinormalizzazione perdono peso i parametri non moltiplicati "
                       "(vie di fuga, fronti attivi, punti di aiuto). Dove questi sono bassi e visuale e uso del suolo "
                       "alti, S sale di poco anche al buio. Cambiare solo i moltiplicatori non basta: con luce ×2 i tratti "
                       f"restano {left[2.0]}, con luce ×3 {left[3.0]}. Per garantire il controllo serve una penalità di buio "
                       "specifica del profilo: è una decisione del team. Il costo per il navigatore invece cresce sempre "
                       "(controllo successivo).")
        checks.append({"controllo": name, "esito": "PASS" if n_up == 0 else "FAIL", "dettaglio": detail})
        cost_d = donna.loc[poor, "costo_per_m"]
        cost_r = sera.loc[poor, "costo_per_m"]
        n_lower = int((cost_d < cost_r - 1e-9).sum())
        checks.append({"controllo": "(aggiuntivo) Sui tratti con luce scarsa il costo per metro del profilo donna non è mai "
                                    "inferiore al riferimento",
                       "esito": "PASS" if n_lower == 0 else "FAIL",
                       "dettaglio": f"costo medio per metro {cost_d.mean():.2f} (donna, λ = 3) contro {cost_r.mean():.2f} "
                                    f"(riferimento, λ = 1,5); tratti con costo inferiore: {n_lower}"})
    else:
        checks.append({"controllo": name, "esito": "FAIL", "dettaglio": "nessun tratto con luce misurata < 0,5 di sera"})

    # 5-6. ranges and NaN
    out_of_range = int(((scores["S"] < 0) | (scores["S"] > 100)).sum())
    checks.append({"controllo": "Nessun tratto ha S fuori da 0–100", "esito": "PASS" if out_of_range == 0 else "FAIL",
                   "dettaglio": f"{out_of_range} valori fuori intervallo su {len(scores):,}"})
    n_nan = int(scores[["S", "affidabilita", "costo_per_m"]].isna().sum().sum())
    checks.append({"controllo": "Nessun NaN nei punteggi", "esito": "PASS" if n_nan == 0 else "FAIL",
                   "dettaglio": f"{n_nan} valori mancanti in S, affidabilità e costo"})
    return checks


CENTRE_DESCRIPTION = ""


def _historic_centre(feats: gpd.GeoDataFrame, cfg: dict[str, Any]):
    """Historic centre: OSM polygon if mapped, else 600 m around Piazza dei Signori."""
    global CENTRE_DESCRIPTION
    poly = feats[feats.geom_type.isin(["Polygon", "MultiPolygon"])]
    names = poly.get("name", pd.Series(index=poly.index, dtype=object)).fillna("").str.lower()
    cand = poly[names.str.contains("centro storico")]
    if len(cand):
        CENTRE_DESCRIPTION = "poligono OSM «centro storico»"
        return cand.union_all()
    piazza = feats[feats.get("name", pd.Series(index=feats.index, dtype=object)).fillna("").eq("Piazza dei Signori")]
    if len(piazza):
        CENTRE_DESCRIPTION = "entro 600 m da Piazza dei Signori (OSM)"
        return piazza.geometry.iloc[0].centroid.buffer(600)
    CENTRE_DESCRIPTION = "entro 600 m da Piazza dei Signori (coordinate fisse)"
    c = gpd.GeoSeries.from_xy([11.5469], [45.5470], crs="EPSG:4326").to_crs(cfg["area"]["crs_metric"]).iloc[0]
    return c.buffer(600)


def flag_summary(params: pd.DataFrame, cfg: dict[str, Any]) -> pd.DataFrame:
    keys = [p["key"] for p in cfg["parameters"]]
    labels = {p["key"]: p["label"] for p in cfg["parameters"]}
    sera = params[params["fascia"] == "sera"]
    rows = []
    for k in keys:
        counts = sera[f"flag_{k}"].astype(str).value_counts(normalize=True) * 100
        rows.append({"parametro": labels[k], "measured %": counts.get("measured", 0.0),
                     "proxy %": counts.get("proxy", 0.0), "excluded %": counts.get("excluded", 0.0),
                     "valore medio": sera[f"x_{k}"].mean()})
    return pd.DataFrame(rows)


def score_map(segments: gpd.GeoDataFrame, scores: pd.DataFrame, quartieri: gpd.GeoDataFrame, boundary,
              cfg: dict[str, Any], out: Path) -> Path:
    """Folium map with a band/profile selector; scores are stored once per combination."""
    from model.config import param_labels

    labels = param_labels(cfg)
    keys = [p["key"] for p in cfg["parameters"]]
    seg = segments.reset_index(drop=True)
    index = {sid: i for i, sid in enumerate(seg["segment_id"])}
    data = _geojson_lines(seg, ["via", "quartiere", "classe", "lunghezza_m"])
    combos = {}
    for (band, profile), sc in scores.groupby(["fascia", "profilo"], sort=False):
        S = np.full(len(seg), -1.0)
        R = np.zeros(len(seg))
        W = [""] * len(seg)
        idx = sc["segment_id"].map(index).to_numpy()
        S[idx] = sc["S"].round(1).to_numpy()
        R[idx] = sc["affidabilita"].round(2).to_numpy()
        for j, w in zip(idx, sc["peggiori"]):
            W[j] = ",".join(str(keys.index(k)) for k in w.split(",") if k)
        combos[f"{band}|{profile}"] = {"S": S.tolist(), "R": R.tolist(), "W": W}
    bands = list(dict.fromkeys(scores["fascia"]))
    profiles = list(dict.fromkeys(scores["profilo"]))
    band_labels = {b: cfg["timebands"]["bands"][b]["label"] for b in bands}
    profile_labels = {p: " + ".join(cfg["profiles"][q]["label"] for q in p.split("+")) for p in profiles}
    cls = cfg["scoring"]["classes"]
    m = _base_map(boundary)
    folium.GeoJson(quartieri.__geo_interface__, name="Quartieri",
                   style_function=lambda _: {"color": "#666", "weight": 1, "fillOpacity": 0.0},
                   tooltip=folium.GeoJsonTooltip(fields=["quartiere"], aliases=["Quartiere"])).add_to(m)
    mapname = m.get_name()
    js = f"""
    var segData = {json.dumps(data, separators=(',', ':'))};
    var combos = {json.dumps(combos, separators=(',', ':'))};
    var paramLabels = {json.dumps([labels[k] for k in keys], ensure_ascii=False)};
    var bandLabels = {json.dumps(band_labels, ensure_ascii=False)};
    var profileLabels = {json.dumps(profile_labels, ensure_ascii=False)};
    var current = '{bands[1] if len(bands) > 1 else bands[0]}|{profiles[0]}';
    function colorFor(s) {{
        if (s < 0) return '#bbbbbb';
        if (s < {cls['red_below']}) return '{cls['colors']['rossa']}';
        if (s > {cls['green_above']}) return '{cls['colors']['verde']}';
        return '{cls['colors']['gialla']}';
    }}
    var segLayer = L.geoJSON(segData, {{
        style: function(f) {{ return {{color: colorFor(combos[current].S[f.properties.i]), weight: 2.5, opacity: 0.9}}; }},
        onEachFeature: function(f, layer) {{
            layer.bindTooltip(function() {{
                var c = combos[current], i = f.properties.i;
                var worst = c.W[i] ? c.W[i].split(',').map(function(k) {{ return paramLabels[+k]; }}).join(', ') : '–';
                return '<b>' + f.properties.via + '</b> <small>(' + f.properties.quartiere + ')</small><br>' +
                       'S = <b>' + c.S[i].toFixed(1) + '</b> &nbsp; affidabilità ' + c.R[i].toFixed(2) + '<br>' +
                       'parametri peggiori: ' + worst;
            }}, {{sticky: true}});
        }}
    }}).addTo({mapname});
    function restyle() {{ segLayer.setStyle(function(f) {{ return {{color: colorFor(combos[current].S[f.properties.i]), weight: 2.5, opacity: 0.9}}; }}); }}
    var ctl = L.control({{position: 'topright'}});
    ctl.onAdd = function() {{
        var d = L.DomUtil.create('div');
        d.style.cssText = 'background:white;padding:8px;font:13px sans-serif;border-radius:4px;box-shadow:0 1px 4px rgba(0,0,0,.3)';
        var parts = current.split('|');
        d.innerHTML = '<b>Fascia</b><br><select id="selBand">' + Object.keys(bandLabels).map(function(b) {{
              return '<option value="' + b + '"' + (b === parts[0] ? ' selected' : '') + '>' + bandLabels[b] + '</option>'; }}).join('') +
            '</select><br><b>Profilo</b><br><select id="selProfile">' + Object.keys(profileLabels).map(function(p) {{
              return '<option value="' + p + '"' + (p === parts[1] ? ' selected' : '') + '>' + profileLabels[p] + '</option>'; }}).join('') +
            '</select><div style="margin-top:6px">' +
            '<span style="color:{cls['colors']['verde']}">&#9632;</span> S &gt; {cls['green_above']} &nbsp;' +
            '<span style="color:{cls['colors']['gialla']}">&#9632;</span> {cls['red_below']}–{cls['green_above']} &nbsp;' +
            '<span style="color:{cls['colors']['rossa']}">&#9632;</span> &lt; {cls['red_below']}</div>' +
            '<div style="max-width:220px;margin-top:4px;color:#555;font-size:11px">Stima della sicurezza percepita dai dati pubblici: ' +
            'indica priorità di intervento, non la sicurezza reale.</div>';
        L.DomEvent.disableClickPropagation(d);
        return d;
    }};
    ctl.addTo({mapname});
    function onSel() {{ current = document.getElementById('selBand').value + '|' + document.getElementById('selProfile').value; restyle(); }}
    document.addEventListener('change', function(e) {{ if (e.target.id === 'selBand' || e.target.id === 'selProfile') onSel(); }});
    """
    _MapScript(js).add_to(m)
    folium.LayerControl(position="topleft").add_to(m)
    out.parent.mkdir(parents=True, exist_ok=True)
    m.save(str(out))
    log.info("mappa di controllo: %s", out)
    return out


def validation_markdown(segments, params, scores, streets, quartieri_agg, checks, cov, meta, cfg) -> str:
    from pipeline import aggregate  # noqa: F401

    labels = {p["key"]: p["label"] for p in cfg["parameters"]}
    lines = [
        "# Validazione del punteggio — Vicenza",
        "",
        DISCLAIMER,
        "",
        f"Dati OSM al {meta.get('osm_timestamp')} (fonte: {meta.get('source')}). Data di riferimento: "
        f"{cfg['standard']['reference_date']} (feriale), ore di riferimento per fascia: "
        + ", ".join(f"{b} {t}" for b, t in cfg["standard"]["band_times"].items() if b in cfg["standard"]["bands"]) + ".",
        "",
        "Nei testi si parla di **criticità percepite** e **priorità di intervento**: il punteggio non individua zone pericolose.",
        "",
        "## Controlli di coerenza",
        "",
        _md_table(pd.DataFrame(checks)[["controllo", "esito", "dettaglio"]]),
        "",
        "## Copertura dei dati",
        "",
        f"- Tratti pedonali: {cov['tratti']:,} ({cov['lunghezza_km']} km); tratti con `lit`: "
        f"{cov['lit']['con_tag']['lunghezza_pct']}% della lunghezza; lampioni OSM: {cov['lampioni_osm']:,}; "
        f"attività con `opening_hours`: {cov['poi']['con_opening_hours_pct']}% di {cov['poi']['totale']:,}; "
        f"strade veicolari con `sidewalk`: {cov['sidewalk']['strade_veicolari_con_tag_sidewalk']['lunghezza_pct']}%.",
        "- Dettaglio completo in `reports/osm_coverage.md`; stato delle fonti in `DATA_SOURCES.md`.",
        "",
        "### Origine dei valori per parametro (fascia sera, % dei tratti)",
        "",
        _md_table(flag_summary(params, cfg), "{:.1f}"),
        "",
        "## Distribuzione di S per fascia e profilo",
        "",
    ]
    dist = scores.groupby(["fascia", "profilo"], sort=False)["S"].describe(percentiles=[0.1, 0.5, 0.9]).reset_index()
    red = scores.assign(r=scores["classe_colore"].eq("rossa"), g=scores["classe_colore"].eq("verde")).groupby(
        ["fascia", "profilo"], sort=False)[["r", "g"]].mean().mul(100).reset_index()
    dist = dist.merge(red, on=["fascia", "profilo"])
    dist = dist.rename(columns={"mean": "media", "10%": "p10", "50%": "mediana", "90%": "p90", "r": "% rossi", "g": "% verdi"})
    lines.append(_md_table(dist[["fascia", "profilo", "media", "p10", "mediana", "p90", "min", "max", "% rossi", "% verdi"]]))
    lines += ["", "S cambia poco da un profilo all'altro, come previsto dal modello (PDF, esempio di calcolo): i profili "
              "spostano peso tra parametri, quindi S cambia solo dove un parametro molto pesato per quel profilo è "
              "molto diverso dagli altri. Over 75 e disabilità hanno S medio più alto perché pesano molto la qualità "
              "del percorso, che in media è buona. L'effetto principale del profilo è sul **costo per il navigatore** "
              "(λ): stesso tratto, costo più alto per chi è più sensibile al rischio.", "",
              "### Costo medio per metro (C/L) per fascia e profilo", ""]
    cost = scores.groupby(["fascia", "profilo"], sort=False)["costo_per_m"].mean().unstack("profilo").reset_index()
    lines.append(_md_table(cost, "{:.2f}"))
    lines += ["", "### Affidabilità media per fascia", ""]
    rel = params.groupby("fascia", sort=False)["affidabilita"].agg(["mean", "min", "max"]).reset_index()
    lines.append(_md_table(rel.rename(columns={"mean": "media"}), "{:.2f}"))
    lines += ["", "## Affidabilità media e S per quartiere (sera, riferimento)", ""]
    q = quartieri_agg[(quartieri_agg["fascia"] == "sera") & (quartieri_agg["profilo"] == "riferimento")]
    q = q.sort_values("S_medio")[["quartiere", "tratti", "lunghezza_km", "S_medio", "pct_lunghezza_rossa", "affidabilita_media"]]
    lines.append(_md_table(q, "{:.2f}"))
    for band in cfg["standard"]["bands"]:
        st = streets[(streets["fascia"] == band) & (streets["profilo"] == "riferimento")
                     & (streets["via"] != cfg["network"]["unnamed_label"]) & (streets["lunghezza_m"] >= 100)]
        cols = ["via", "quartiere", "lunghezza_m", "S_medio", "S_min", "pct_lunghezza_rossa", "affidabilita_media"]
        lines += ["", f"## Le 20 vie con S più alto — {cfg['timebands']['bands'][band]['label'].lower()} (riferimento, vie ≥ 100 m)", ""]
        lines.append(_md_table(st.sort_values("S_medio", ascending=False).head(20)[cols]))
        lines += ["", f"## Le 20 vie con S più basso (priorità di intervento) — {cfg['timebands']['bands'][band]['label'].lower()}", ""]
        lines.append(_md_table(st.sort_values("S_medio").head(20)[cols]))
    lines += ["", "## Parametri esclusi", "",
              "Episodi segnalati, cura e degrado, composizione della folla: nessuna fonte pubblica. "
              "Sono esclusi e i pesi sono rinormalizzati sugli altri (`unmeasured_strategy: renormalize`). "
              "Si attiveranno con le segnalazioni dei cittadini (fase 5).", ""]
    return "\n".join(lines)


def run(cfg: dict[str, Any] | None = None) -> None:
    from pipeline import aggregate
    from pipeline import osm as osm_mod
    from pipeline import params as params_mod
    from pipeline import segments as seg_mod

    cfg = cfg or load_config()
    segments = seg_mod.load_segments()
    quartieri = seg_mod.load_quartieri()
    params = pd.read_parquet(params_mod.PARAMS)
    scores = pd.read_parquet(aggregate.SCORES)
    streets = aggregate.aggregate_streets(segments, scores)
    q_agg = aggregate.aggregate_neighbourhoods(segments, scores, streets)
    meta = json.loads(osm_mod.META.read_text(encoding="utf-8"))
    cov = json.loads(COVERAGE_JSON.read_text(encoding="utf-8"))
    checks = coherence_checks(segments, params, scores, cfg)
    md = validation_markdown(segments, params, scores, streets, q_agg, checks, cov, meta, cfg)
    (REPORTS / "validation.md").write_text(md, encoding="utf-8")
    boundary = osm_mod.load_boundary().geometry.iloc[0]
    score_map(segments, scores, quartieri, boundary, cfg, REPORTS / "check_map.html")
    for c in checks:
        log.info("%s — %s", c["esito"], c["controllo"])
