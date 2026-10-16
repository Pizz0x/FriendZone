# Quartieri Vivi (titolo provvisorio) — backend

Backend dell'hackathon **TechWarriors Vicenza 2026**, sfida 07 – Urbanistica.
Calcola un **punteggio di sicurezza percepita stimata** (S, da 0 a 100) per ogni
tratto della rete pedonale di Vicenza, poi per via e per quartiere, partendo
solo da fonti pubbliche. Il modello è descritto in `docs/modello_punteggio.pdf`
(bozza del team) e corretto da `BRIEF.md`: dove non coincidono vale il brief.

> Il punteggio stima la sicurezza percepita a partire dai dati disponibili.
> Non misura la sicurezza reale di un luogo. Nei materiali si parla di
> *criticità percepite* e *priorità di intervento*, mai di "zone pericolose".

## Avvio rapido

Serve Python 3.11.

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m pytest                      # test (70, nessuna rete richiesta)
python -m pipeline.run_all            # pipeline completa, con cache dei download
```

I risultati sono già nel repository: per guardarli non serve eseguire la pipeline.

| Per… | Apri |
|---|---|
| vedere la mappa | `reports/check_map.html` nel browser (serve internet per Leaflet e lo sfondo OSM). In alto a destra si scelgono fascia e profilo; passando sopra un tratto si leggono via, S, affidabilità, i 3 parametri che pesano di più e da dove viene il dato sulla luce |
| controllare i risultati in kepler.gl o geojson.io | `exports/segments_{fascia}_{profilo}.geojson` (proprietà `S`, `classe_colore`, `colore`, `affidabilita`, `parametri_peggiori`, `fonte_luce`) |
| leggere i controlli | `reports/validation.md` e `reports/osm_coverage.md` |
| tabelle per via e quartiere | `exports/vie.csv`, `exports/quartieri.csv` (con i residenti esposti) |
| sapere da dove vengono i dati | `DATA_SOURCES.md`, `docs/illuminazione.md` |
| sapere come passare ai dati reali | `docs/piano_dati_reali.md` |

### Scenari per la demo

```bash
# qualsiasi data, ora, profilo e meteo (scrive exports/scenario_*.geojson e stampa un riepilogo)
python -m pipeline.scenario --datetime 2026-11-20T21:30 --profilo donna --meteo pioggia
# aggiunge i tre eventi SIMULATI di data/demo/ (il risultato riporta scenario_demo: true)
python -m pipeline.scenario --datetime 2026-11-18T21:00 --profilo donna --demo
```

Senza `--meteo` il meteo viene da Open-Meteo; se non è raggiungibile si usa `sereno` e
il riepilogo lo dice. Gli eventi simulati non entrano mai nei calcoli senza `--demo`.

### Opzioni della pipeline

```bash
python -m pipeline.run_all --until segments   # si ferma dopo un passo: sources, osm, segments, params, aggregate, validate
python -m pipeline.run_all --force            # riscarica i dati OSM
python -m pipeline.run_all --planet           # se Overpass non risponde: estrae Vicenza dal planet OSM su AWS (~25 min, serve osmium-tool)
python -m pipeline.run_all --skip-probe       # salta la verifica di raggiungibilità delle fonti
```

Il primo tentativo è sempre Overpass via osmnx. Se non risponde, la pipeline usa un
estratto locale (`data/manual/osm/vicenza.osm.pbf` fornito a mano, oppure
`data/raw/osm/vicenza_bbox.osm.pbf` creato con `--planet`). Le fonti mancanti si
sbloccano mettendo i file in `data/manual/` (istruzioni in `docs/piano_dati_reali.md`).

L'API FastAPI (`uvicorn api.main:app`) è prevista nella fase 4 e non c'è ancora; userà
`pipeline.scenario.Engine` per le combinazioni non precalcolate.

## Struttura

| Percorso | Contenuto |
|---|---|
| `config.yaml` | tutto il modello: pesi, profili, fasce, soglie, mappature, orari predefiniti, URL |
| `model/scoring.py` | pesi per fascia e profilo, S, penalità, costo, classi, affidabilità, parametri peggiori |
| `model/timebands.py` | fasce orarie dal tramonto (astral), feriale/weekend con festivi |
| `model/dynamic.py` | meteo (Open-Meteo con cache e override) ed eventi (±1 h, 300 m) |
| `pipeline/osm.py` | OSM: Overpass/osmnx oppure estratto locale (pyosmium) |
| `pipeline/planet_stream.py` | download parallelo del planet OSM da AWS, in streaming verso osmium |
| `pipeline/segments.py` | tratti pedonali e quartieri |
| `pipeline/pois.py` | attività (OSM + Overture), orari di apertura, fermate, parchi, uso del suolo |
| `pipeline/sources_public.py` | SIT, ISTAT, popolazione HRSL, luoghi Overture, Punti Viola, punti luce, verifica delle fonti |
| `pipeline/light_model.py` | stima della luce dove OSM non ha dati |
| `pipeline/params.py` | i 12 parametri per tratto e fascia, con flag, penalità e affidabilità |
| `pipeline/aggregate.py` | punteggi delle combinazioni standard, aggregati per via e quartiere, residenti esposti, export |
| `pipeline/validate.py` | report di copertura, `validation.md`, mappa di controllo |
| `pipeline/scenario.py` | punteggi per data/ora/profilo/meteo qualsiasi, scenario demo |
| `data/processed/` | `segments.parquet`, `params.parquet`, `scores.parquet`, `quartieri.parquet` (GeoParquet) |
| `data/demo/` | solo dati **simulati** per la demo (eventi), usati solo con `--demo` |
| `tests/` | test del modello, delle fasce, dei parametri, del modulo dinamico (dati sintetici) e del percorso Overpass simulato |

## Scelte di implementazione

Dove il brief lascia margine, ecco cosa è stato deciso (tutti i numeri sono in `config.yaml`):

- **Tratti**: grafo pedonale non orientato e semplificato; oltre che agli incroci, un
  tratto si spezza dove cambiano nome o classe della strada, così ogni tratto
  appartiene a una sola via. Le vie sono "stesso nome nello stesso quartiere"; i tratti
  senza nome restano singoli ("percorso senza nome").
- **Rete pedonale**: filtro `walk` di osmnx, più una regola italiana: escluse
  `motorroad=yes` e `highway=trunk` senza marciapiede (art. 175 del Codice della
  strada). Così escono le tangenziali (circa 34 km).
- **Fasce**: i parametri che dipendono dall'ora (aperture, mezzi) sono valutati a un'ora
  rappresentativa della data di riferimento, mercoledì 18/11/2026: giorno 11:00, sera
  20:00 (come l'esempio del PDF), notte fonda 23:30. Venerdì sera, sabato, domenica e
  festivi contano come weekend; le ore prima delle 05:00 appartengono alla sera prima.
- **Luce**: punti luce SIT (se arrivano) > `lit` del tratto > `lit` di una via adiacente
  entro 12 m > lampioni OSM, solo se almeno uno è entro 20 m > **stima statistica**
  addestrata sui tratti con `lit` noto. Le ultime tre sono `proxy`; ogni tratto porta
  `fonte_luce`.
- **Persone** (proxy): 0,5 × attività aperte entro 50 m + 0,2 × fermate entro 100 m
  pesate per la frequenza della fascia + 0,3 × residenti entro 100 m (popolazione Meta
  HRSL, perché ISTAT non era raggiungibile). Il totale è normalizzato sul massimo della
  città (99° percentile di tutte le fasce del giorno), come chiede il PDF.
- **Attività**: OSM più Overture Places, senza doppioni. Senza orario si usano gli orari
  predefiniti per categoria e il parametro diventa `proxy`.
- **Fronti attivi**: `measured` se tutte le attività entro 25 m hanno `opening_hours`,
  `proxy` se almeno una usa gli orari predefiniti.
- **Visuale** (proxy): 0,7 meno fino a 0,25 per muri e siepi entro 5 m (le recinzioni
  contano metà), 0,3 per i tratti coperti, 0,4 per i sottopassi, 0,15 se ci sono binari
  entro 20 m.
- **Vie di fuga**: incroci (nodi con almeno 3 strade) agli estremi del tratto ogni
  100 m; tratti oltre 200 m ×0,8; vicolo cieco 0,2; scale al massimo 0,5.
- **Uso del suolo**: punti campione ogni 15 m sul tratto e a 25 m per lato; ogni punto
  prende il poligono più specifico (parco, scuola, parcheggio) rispetto al `landuse`
  generico; escluso se meno del 20% dei punti cade in un'area classificata.
- **Trasporto**: per ogni fermata entro 600 m, distanza × pensilina o luce (×0,85 se
  mancano) × frequenza stimata per fascia; vale la fermata migliore.
- **Penalità −30%**: sottopassi pedonali (`tunnel` o `layer<0`), tratti coperti e
  passaggi sotto edifici (non i portici `covered=arcade/colonnade`), passaggi pedonali
  senza uscita. Le strade carrabili senza uscita hanno solo vie di fuga = 0,2.
  **Penalità −40%**: tratto per almeno metà in un parco, nelle fasce di buio, se il
  parco risulta chiuso da `opening_hours` o la luce è sotto 0,3.
- **Meteo ed eventi**: pioggia → persone ×0,7 e visuale ×0,8; nebbia → visuale ×0,8;
  eventi da un'ora prima a un'ora dopo, entro 300 m: persone +0,3, fronti attivi +0,2,
  punti di aiuto +0,2.

## Stato

Aggiornato alla fine di ogni fase.

### Funziona
- **Fase 0** — `config.yaml` completo; `model/scoring.py` e `model/timebands.py`. L'esempio
  del PDF è riprodotto per intero nei test: A ≈ 79 / 1,07; B ≈ 42 / 1,50; C ≈ 23 / 1,88;
  C da 200 m per donna over 75 ≈ 646 m, più le colonne donna 18–34 e donna over 75.
- **Fase 1** — dati OSM di tutta Vicenza (al 12/10/2026, dal planet su AWS perché
  Overpass non è raggiungibile da qui); 13.728 tratti pedonali (804 km) in
  `segments.parquet`; 38 quartieri; report di copertura; `DATA_SOURCES.md`.
- **Fase 2** — 12 parametri × 5 fasce con flag (`params.parquet`), penalità,
  affidabilità; S per le 15 combinazioni standard (3 fasce × 5 profili); 15 GeoJSON,
  `vie.csv`, `quartieri.csv`; `validation.md` con 7 controlli di coerenza (6 PASS, 1 FAIL
  motivato, vedi sotto); mappa di controllo con selettore di fascia e profilo.
- **Dati per la demo** (dopo la fase 2) — fonti reali alternative a quelle bloccate:
  popolazione Meta HRSL (residenti, donne, over 60) al posto di ISTAT, con i residenti
  esposti per quartiere; 4.493 attività da Overture Places oltre alle 1.174 di OSM; stima
  statistica della luce; `model/dynamic.py` (meteo ed eventi) e `pipeline/scenario.py`
  per qualsiasi data e ora; scenario demo con eventi simulati ed etichettati.
- **Corretto** un bug della fase 2: la normalizzazione delle persone, dalla seconda fascia
  in poi, finiva sulla colonna del trasporto. Un test di regressione lo copre.
- Test: 70, tutti verdi (`python -m pytest`).

### Stimato
- Pesi, moltiplicatori dei profili e λ: proposta ricavata dalla letteratura (PDF), da
  tarare con il questionario.
- **Luce**: misurata solo sull'11% dei tratti (`lit` OSM); il resto è stimato da vie
  adiacenti (8%), lampioni OSM (12%) e dal modello statistico (68%, AUC 0,86, accuratezza
  93% in validazione per quartiere). Va sostituita con i punti luce reali.
- Presenza di persone e visuale libera sono sempre `proxy`; i residenti vengono da HRSL,
  una stima modellata, non un conteggio.
- Orari di apertura: noti solo per il 16% delle attività OSM e per nessuna di Overture;
  altrove orari predefiniti per categoria.
- Frequenza dei mezzi per fascia: stima in config (nessun GTFS di SVT nel catalogo
  Mobility Database).
- Confini dei quartieri: celle di Voronoi attorno ai 38 punti `place` di OSM.
- Eventi: solo lo scenario **simulato** di `data/demo/`, attivo con `--demo`.

### Controllo in FAIL (motivato)
"Il profilo donna non alza mai S sui tratti con luce scarsa": di sera, sui 965 tratti
con luce < 0,5, S scende in 559 ma sale in 406, al massimo di 2,4 punti. È una
proprietà del modello del brief: il profilo aumenta anche i pesi di visuale e uso del
suolo, e dopo la rinormalizzazione perdono peso vie di fuga, fronti attivi e punti di
aiuto. Cambiare solo i moltiplicatori non basta. Per lo stesso motivo il profilo donna
ha in media un S leggermente più alto del riferimento; il **costo per il navigatore**
invece è sempre più alto (λ doppio, controllo aggiuntivo PASS). Se il team vuole
garantire anche S, serve una penalità di buio specifica del profilo.

### Da fare
- **Dati reali** al posto delle stime, a partire dai punti luce: piano e testo della
  richiesta al Comune in `docs/piano_dati_reali.md`. Sulla rete di questo ambiente sono
  bloccati SIT, ISTAT, dati.veneto.it, eventi, Punti Viola e Open-Meteo; da un computer
  del team funzionano.
- **Fase 3** — integrare GTFS SVT, eventi reali, Punti Viola, zonizzazione del PI
  quando arrivano i file; Mapillary e SDGSAT-1 per la luce.
- **Fase 4** — API FastAPI (`api/main.py`) con i suoi test.
- **Fase 5** — segnalazioni (SQLite), `S_percepito`, simulazione in database separato.
