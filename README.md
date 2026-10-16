# Quartieri Vivi (titolo provvisorio) — backend

Backend dell'hackathon **TechWarriors Vicenza 2026**, sfida 07 – Urbanistica.
Calcola un **punteggio di sicurezza percepita stimata** (S, da 0 a 100) per ogni
tratto della rete pedonale di Vicenza, poi per via e per quartiere, partendo
solo da fonti pubbliche. Il modello è descritto in `docs/modello_punteggio.pdf`
(bozza del team) e corretto da `BRIEF.md`: dove non coincidono vale il brief.

> Il punteggio stima la sicurezza percepita a partire dai dati disponibili.
> Non misura la sicurezza reale di un luogo.

## Installazione

Serve Python 3.11.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Solo se Overpass non è raggiungibile (vedi `DATA_SOURCES.md`) serve anche
`osmium-tool` (`apt install osmium-tool`) per estrarre Vicenza dal planet OSM.

## Test

```bash
python -m pytest
```

## Struttura

| Cartella / file | Contenuto |
|---|---|
| `config.yaml` | pesi, profili, fasce, soglie, mappature, URL: tutto il modello è qui |
| `model/scoring.py` | pesi per fascia e profilo, S, penalità, costo, classi, affidabilità |
| `model/timebands.py` | fasce orarie dal tramonto (astral), feriale/weekend |
| `pipeline/` | download e calcolo (fasi 1–3) |
| `api/` | API FastAPI (fase 4) |
| `tests/` | test automatici |

## Stato

Aggiornato alla fine di ogni fase.

### Fase 0 — completata

**Funziona**
- `config.yaml` con i 12 parametri e i pesi giorno/notte, le 5 fasce, i 9 profili
  combinabili, λ, soglie di colore, penalità, fattori di affidabilità, strategia
  per i parametri esclusi (`renormalize` di default, `neutral` in alternativa).
- `model/scoring.py`: pesi personalizzati, S, penalità moltiplicative, costo per
  il navigatore, classi rossa/gialla/verde, affidabilità, parametri peggiori.
- `model/timebands.py`: fasce calcolate dal tramonto di ogni giorno a Vicenza,
  senza il buco di 30 minuti della bozza PDF; feriale/weekend con festivi.
- Test (`pytest`, 47 test): l'esempio del PDF è riprodotto per intero
  (A ≈ 79 / 1,07; B ≈ 42 / 1,50; C ≈ 23 / 1,88; C da 200 m per donna over 75 ≈ 646 m),
  più rinormalizzazione, strategia neutra, confini delle fasce a dicembre e a giugno,
  combinazione dei profili, affidabilità.

**Stimato**
- Pesi, moltiplicatori dei profili e λ: proposta del team ricavata dalla
  letteratura (PDF), non ancora tarata su Vicenza con il questionario.

### Fase 1 — completata

**Funziona**
- Dati OSM di tutta Vicenza (al 12/10/2026). Overpass non è raggiungibile da questo
  ambiente, quindi la pipeline ha estratto Vicenza dal planet OSM su AWS (vedi
  `DATA_SOURCES.md`). Il percorso Overpass + osmnx resta il primo tentativo.
- `data/processed/segments.parquet`: 13.728 tratti pedonali (804 km) del grafo non
  orientato e semplificato, con id, nome, via, classe, lunghezza, quartiere, tag utili
  e geometria.
- `data/processed/quartieri.parquet`: 38 quartieri.
- `reports/osm_coverage.md`: report di copertura (`lit`, lampioni, `opening_hours`,
  `sidewalk`, ecc.).
- `reports/check_map.html`: prima mappa di controllo, con le classi stradali.
- `DATA_SOURCES.md` compilato; ricerca sull'illuminazione in `docs/illuminazione.md`.

**Stimato**
- Confini dei quartieri: celle di Voronoi attorno ai 38 punti `place` di OSM, in
  attesa dei confini del SIT.

**Da fare**
- SIT, ISTAT, GTFS, eventi, Punti Viola: bloccati dalla rete, sbloccabili con file in
  `data/manual/` (fase 3).
