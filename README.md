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
python -m pytest                      # test (73, nessuna rete richiesta)
python -m pipeline.run_all            # pipeline completa, con cache dei download
```

I risultati sono già nel repository: per guardarli non serve eseguire la pipeline.

| Per… | Apri |
|---|---|
| **provare l'interfaccia beta** | `frontend/index.html` nel browser (vedi sotto) |
| vedere la mappa | `reports/check_map.html` nel browser (serve internet per Leaflet e lo sfondo OSM). In alto a destra si scelgono fascia e profilo; passando sopra un tratto si leggono via, S, affidabilità, i 3 parametri che pesano di più e da dove viene il dato sulla luce |
| controllare i risultati in kepler.gl o geojson.io | `exports/segments_{fascia}_{profilo}.geojson` (proprietà `S`, `classe_colore`, `colore`, `affidabilita`, `parametri_peggiori`, `fonte_luce`) |
| leggere i controlli | `reports/validation.md` e `reports/osm_coverage.md` |
| tabelle per via e quartiere | `exports/vie.csv`, `exports/quartieri.csv` (con i residenti esposti) |
| sapere da dove vengono i dati | `DATA_SOURCES.md`, `docs/illuminazione.md` |
| sapere come passare ai dati reali | `docs/piano_dati_reali.md` |

### Interfaccia beta

`frontend/index.html` è una pagina unica, senza server: mappa di Vicenza con **tutti i
13.728 tratti pedonali colorati** (rosso, giallo, verde), ricalcolati nel browser quando
si cambiano:

- **ora** (0–23, con alba e tramonto del 18/11/2026 e la fascia corrispondente) e
  **giorno** feriale o weekend;
- **meteo** (sereno o pioggia);
- **sesso** e **età** (16–34, 35–74, 75+), più i profili aggiuntivi del PDF (disabilità,
  LGBTQ+, molestie recenti, conosce la zona, in compagnia).

Cliccando un tratto si leggono via, quartiere, S, affidabilità, i parametri che pesano
di più e da dove viene il dato sulla luce. Nessun tratto pedonale è grigio: dove manca
un dato misurato c'è una stima dichiarata (`proxy`), indicata nella scheda. In grigio ci
sono solo le strade non percorribili a piedi (tangenziali, superstrade). Il calcolo nel
browser è lo stesso di `model/scoring.py` (differenza massima 0,18 punti, classe uguale
in oltre il 99,9% dei tratti). Serve internet solo per Leaflet e i caratteri; lo sfondo
(confine, quartieri, parchi, acqua) è dentro la pagina.

```bash
python -m pipeline.frontend    # rigenera frontend/index.html dopo la pipeline
```

I parametri che dipendono dall'ora (persone, fronti attivi, punti di aiuto, trasporto)
sono precalcolati per le 24 ore di un mercoledì e di un sabato di novembre; il resto è
statico. Prossimo passo: profili più flessibili (pesi regolabili) e l'API della fase 4.

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
| `pipeline/segments.py` | tratti pedonali e quartieri (22 zone ufficiali ricostruite) |
| `pipeline/pois.py` | attività (OSM + Overture), orari di apertura, fermate, parchi, uso del suolo |
| `pipeline/sources_public.py` | SIT, ISTAT (sezioni 2021), tabelle del Comune su dati.veneto.it, Nominatim, popolazione HRSL, luoghi Overture, Punti Viola, punti luce, verifica delle fonti |
| `pipeline/light_model.py` | stima della luce dove OSM non ha dati |
| `pipeline/params.py` | i 12 parametri per tratto e fascia, con flag, penalità e affidabilità |
| `pipeline/aggregate.py` | punteggi delle combinazioni standard, aggregati per via e quartiere, residenti esposti, export |
| `pipeline/validate.py` | report di copertura, `validation.md`, mappa di controllo |
| `pipeline/scenario.py` | punteggi per data/ora/profilo/meteo qualsiasi, scenario demo |
| `pipeline/frontend.py` | costruisce l'interfaccia beta (`frontend/index.html`) dai dati elaborati |
| `frontend/` | modello della pagina (`template.html`), CSS di Leaflet, pagina generata |
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
  pesate per la frequenza della fascia + 0,3 × residenti entro 100 m (sezioni ISTAT 2021,
  ripartite per area; HRSL solo se ISTAT manca). Il totale è normalizzato sul massimo
  della città (99° percentile di tutte le fasce del giorno), come chiede il PDF.
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
- **Penalità di buio** (aggiunta su richiesta del team): nelle fasce di buio S è
  moltiplicato per (1 − P), con P = intensità della fascia × (0,05 + 0,20 × (1 − luce)) ×
  fattore del profilo, al massimo 0,60. Intensità: 0 di giorno, 0,5 nella prima ora di
  buio, 1 dopo. Fattore: 1 riferimento, **2 donna** (ISTAT 2022-23: si sente insicura da
  sola di sera il 16,4% delle donne contro il 7,4% degli uomini), 1,3 over 75,
  disabilità, LGBTQ+ e molestie recenti, 0,8 chi conosce la zona, 0,5 in compagnia; i
  fattori si moltiplicano. Esempio: tratto buio (luce 0) di sera, donna: −50%; tratto ben
  illuminato: −10%. Valori in `config.yaml -> scoring.penalties.dark`.
- **Quartieri**: le 22 zone ufficiali del Comune (elenco su dati.veneto.it) con confini
  ricostruiti dalle sezioni ISTAT 2021: ogni sezione va a una zona della sua
  circoscrizione, finché la popolazione di ogni zona torna con quella del Comune
  (scarto mediano 1,1%). Da sostituire con i confini del SIT.
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
  Overpass rifiuta le connessioni da questo ambiente); 13.728 tratti pedonali (804 km) in
  `segments.parquet`; **22 quartieri ufficiali**; report di copertura; `DATA_SOURCES.md`.
- **Fase 2** — 12 parametri × 5 fasce con flag (`params.parquet`), penalità,
  affidabilità; S per le 15 combinazioni standard (3 fasce × 5 profili); 15 GeoJSON,
  `vie.csv`, `quartieri.csv`; `validation.md` con **7 controlli di coerenza, tutti PASS**;
  mappa di controllo con selettore di fascia e profilo.
- **Fonti reali** (rete aperta, 16/10/2026): **sezioni ISTAT 2021** (residenti, residenti
  esposti, circoscrizioni) e **tabelle del Comune** su dati.veneto.it (22 zone,
  residenti per quartiere, sesso ed età); 4.493 attività da Overture Places oltre alle
  1.174 di OSM; stima statistica della luce; `model/dynamic.py` (meteo ed eventi) e
  `pipeline/scenario.py` per qualsiasi data e ora; scenario demo con eventi simulati ed
  etichettati.
- **Penalità di buio** dipendente da luce, fascia e profilo (vedi sopra). Ha risolto il
  controllo che prima era in FAIL: di sera, sui 965 tratti con luce < 0,5, il profilo
  donna ha S più basso del riferimento su tutti (in media −6,5 punti).
- **Residenti esposti** (sezioni ISTAT attraversate da almeno un tratto rosso, di sera,
  riferimento): 59.480 su 110.293 (54%), di cui circa 30.600 donne e 20.000 over 60.
  Contano anche tratti rossi molto brevi: è un indicatore di priorità, non di rischio.
- **Interfaccia beta** (`frontend/index.html`): mappa con tutti i tratti colorati, ora,
  giorno, meteo, sesso, età e profili aggiuntivi.
- **Corretto** un bug della fase 2: la normalizzazione delle persone, dalla seconda fascia
  in poi, finiva sulla colonna del trasporto. Un test di regressione lo copre.
- Test: 73, tutti verdi (`python -m pytest`).

### Stimato
- Pesi, moltiplicatori dei profili, λ e **penalità di buio**: proposta ricavata dalla
  letteratura (PDF, ISTAT), da tarare con il questionario.
- **Luce**: misurata solo sull'11% dei tratti (`lit` OSM); il resto è stimato da vie
  adiacenti (8%), lampioni OSM (12%) e dal modello statistico (68%, AUC 0,87, accuratezza
  93% in validazione per quartiere). Va sostituita con i punti luce reali.
- Presenza di persone e visuale libera sono sempre `proxy`.
- Orari di apertura: noti solo per il 16% delle attività OSM e per nessuna di Overture;
  altrove orari predefiniti per categoria.
- Frequenza dei mezzi per fascia: stima in config (nessun GTFS pubblico di SVT; di sera
  il servizio è a chiamata).
- Confini dei 22 quartieri: ricostruiti da dati ufficiali (ISTAT + Comune), non ancora
  quelli del SIT.
- Donne e over 60 esposti: quote per quartiere del Comune applicate ai residenti ISTAT.
- Meteo: qui Open-Meteo risponde 429 (limite dell'indirizzo condiviso), quindi `sereno`
  dichiarato; dal computer del team funziona.
- Eventi: solo lo scenario **simulato** di `data/demo/`, attivo con `--demo`.

### Da fare
- **Dati reali** al posto delle stime, a partire dai punti luce: piano e testo della
  richiesta al Comune in `docs/piano_dati_reali.md`. Da questo ambiente non arrivano
  Overpass e SIT (rifiutano la connessione); eventi (robots.txt), GTFS SVT, Punti Viola e
  punti luce non sono pubblici.
- **Fase 3** — integrare GTFS SVT, eventi reali, Punti Viola, confini e zonizzazione dal
  SIT quando arrivano i file; Mapillary e SDGSAT-1 per la luce.
- **Fase 4** — API FastAPI (`api/main.py`) con i suoi test; profili più flessibili
  nell'interfaccia.
- **Fase 5** — segnalazioni (SQLite), `S_percepito`, simulazione in database separato.
