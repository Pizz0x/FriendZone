# Fonti dati

Stato al **16 ottobre 2026** (orari UTC). Ogni tentativo di download viene
registrato dalla pipeline in `data/raw/sources_log.json`. Come passare ai dati reali
dove oggi c'è un sostituto: [`docs/piano_dati_reali.md`](docs/piano_dati_reali.md).

> **Vincolo di rete.** L'ambiente cloud in cui è stato sviluppato il backend ha una
> policy di rete che **rifiuta le connessioni** (HTTP 403 sul CONNECT) verso quasi tutte
> le fonti del brief: Overpass, Nominatim, SIT, ISTAT, dati.veneto.it, Open-Meteo, eventi
> del Comune, Geoportale della Provincia, Mobility Database, Transitland, IDT2. Non è un
> blocco dei siti: da un computer del team funzionano. Erano raggiungibili invece **AWS
> S3** e **Google Cloud Storage**, da cui vengono OSM (planet), la popolazione Meta HRSL,
> i luoghi Overture e il catalogo GTFS di Mobility Database.

## Riepilogo

| # | Fonte | Stato | Usata per | Flag |
|---|---|---|---|---|
| 1 | OpenStreetMap | **usata** (planet AWS, dati al 12/10/2026) | rete pedonale, quasi tutti i parametri, quartieri | measured / proxy |
| 2 | SIT VI 2.0 (Comune) | non raggiungibile | — (quartieri, PI, punti luce previsti) | — |
| 3 | ISTAT basi territoriali | non raggiungibile → **sostituita da Meta HRSL** | residenti (presenza di persone), residenti esposti | proxy |
| 4 | dati.veneto.it | non raggiungibile | — | — |
| 5 | Geoportale Provincia di Vicenza | non raggiungibile | — | — |
| 6 | GTFS bus urbani | catalogo Mobility Database letto da GCS: **nessun feed per Vicenza** | — | frequenza stimata: proxy |
| 7 | Eventi del Comune | non raggiungibile | solo scenario demo simulato (`--demo`) | — |
| 8 | Punti Viola (DonneXStrada) | non raggiungibile, nessun file manuale | — | — |
| 9 | Open-Meteo / astral | Open-Meteo non raggiungibile (client pronto, ripiego dichiarato); astral ok | fasce orarie; meteo su richiesta | — |
| 10 | Carta Tecnica Regionale (IDT2) | non raggiungibile (opzionale, fase 6) | — | — |
| + | **Meta / CIESIN HRSL** (AWS) | **usata** | popolazione totale, donne, over 60 a ~30 m | proxy |
| + | **Overture Maps Places** (AWS) | **usata** | 4.493 negozi e locali in più di OSM, punti di aiuto | proxy (orari predefiniti) |
| + | **Stima della luce** (modello su dati OSM) | **usata** | luce dove OSM non ha dati (68% dei tratti) | proxy |

## 1. OpenStreetMap — obbligatoria

- **URL usato**: `https://osm-pds.s3.amazonaws.com/planet-latest.osm.pbf` (registro
  AWS Open Data, bucket `osm-pds`): planet settimanale generato da
  `planet-dump-ng`, **timestamp di replica 2026-10-12T00:00:02Z**.
- **Metodo**: Overpass non raggiungibile da nessuno dei tre endpoint configurati
  (`overpass-api.de`, `overpass.kumi.systems`, `overpass.private.coffee`). Il planet
  (95,4 GB) è stato letto in streaming con `pipeline/planet_stream.py` (download
  parallelo per intervalli di byte, 70–80 MB/s) e filtrato con
  `osmium extract --strategy simple` sul riquadro 11,38–11,70 E / 45,44–45,66 N, senza
  salvare il planet su disco (23 minuti). Risultato: `data/raw/osm/vicenza_bbox.osm.pbf`
  (13,7 MB; 1,39 milioni di nodi, 211 mila vie, 2.465 relazioni).
- **Download**: 16/10/2026, 15:11–15:34 UTC.
- **Licenza**: ODbL 1.0 — © OpenStreetMap contributors. Gli export derivati vanno
  attribuiti e condivisi con la stessa licenza.
- **Cosa è stato usato**: confine comunale (relazione 45159, `admin_level=8`); rete
  pedonale con il filtro `walk` di osmnx replicato in Python (`pipeline/osm.py`), più una
  regola italiana: escluse `motorroad=yes` e `highway=trunk` senza marciapiede (strade
  extraurbane principali, vietate ai pedoni dall'art. 175 del Codice della strada;
  disattivabile con `network.italian_road_rule`); lampioni, `lit`, negozi e amenity con
  `opening_hours`, fermate e stazioni con `shelter`, panchine, muri/siepi/recinzioni,
  binari, `landuse`, parchi e `leisure`, edifici, `place`.
- **Copertura** (dettaglio in `reports/osm_coverage.md`): 13.728 tratti, 804 km;
  `lit` sul 12% della lunghezza; 2.835 lampioni; 999 attività di cui solo il 15,7% con
  `opening_hours`; `sidewalk` sull'11% delle strade veicolari; `surface` sul 66%;
  `landuse` sul 74% della superficie comunale; 401 fermate (295 con `shelter`).
- **Problemi**: pochi negozi mappati (418 `shop=*`), compensati con Overture (sotto). Il
  percorso Overpass + osmnx è implementato ma da qui è stato provato solo con risposte
  simulate (`tests/test_osm_paths.py`).

## 2. SIT VI 2.0 — Comune di Vicenza

- **URL**: `https://sit.comune.vicenza.it/` — connessione rifiutata (16/10/2026 15:35 UTC).
- **Effetto**: quartieri approssimati da OSM (sotto); zonizzazione del PI sostituita da
  `landuse` OSM; nessun punto luce.
- **Come sbloccare**: file in `data/manual/sit/` (shapefile con `.prj`, GeoPackage o
  GeoJSON). Per i quartieri la pipeline cerca nomi di file con "quart", "circoscr" o
  "zone"; se manca il `.prj` assume EPSG:3003 e controlla che il centroide cada su
  Vicenza. Per il PI servirà la legenda dei codici di zona (`pi_zone_map` in config).
- **Licenza**: da verificare sul portale.

### Quartieri (fallback)
OSM non ha poligoni di quartiere né confini di livello 9/10 per Vicenza, ma ha **38 nodi
`place=suburb/quarter/neighbourhood`** (Centro storico, San Pio X, Laghetto, Villaggio
del Sole, Ferrovieri, …): i confini sono **approssimati con celle di Voronoi** attorno a
questi punti, ritagliate sul confine comunale. Vanno sostituiti con quelli del SIT.

## 3. ISTAT → Meta / CIESIN HRSL

- **ISTAT** (`https://www.istat.it/`): connessione rifiutata. Il codice per leggere
  sezioni di censimento e popolazione da `data/manual/istat/` è pronto (filtra
  `PRO_COM = 24116`) e ha la precedenza appena i file ci sono.
- **Sostituto in uso: High Resolution Settlement Layer** (Data for Good at Meta e
  CIESIN, Columbia University), GeoTIFF cloud-optimised sul registro AWS Open Data:
  `https://dataforgood-fb-data.s3.amazonaws.com/hrsl-cogs/` (livelli `general`, `women`,
  `elderly_60_plus`, versione `latest`). Risoluzione 1 secondo d'arco (~30 m).
  Letto il 16/10/2026 solo per la finestra di Vicenza (`data/raw/hrsl/`).
- **Licenza**: CC BY 4.0.
- **Verifica**: dentro il confine comunale HRSL somma **112.429 residenti** (Vicenza ne
  ha circa 111 mila), di cui 59.375 donne e 32.924 over 60.
- **Uso**: componente "residenti" della presenza di persone (somma entro 100 m,
  normalizzata sul 90° percentile); residenti, donne e over 60 entro 100 m da tratti
  rossi per quartiere (`exports/quartieri.csv`). È una stima modellata (censimento +
  edifici da satellite), non un conteggio: flag `proxy`.

## 4. dati.veneto.it — opzionale

- **URL**: `https://dati.veneto.it/api/3/action/package_search?q=vicenza` (API CKAN) —
  connessione rifiutata. Nessun dataset elencato o integrato.

## 5. Geoportale della Provincia di Vicenza — opzionale

- **URL**: `https://geoportale.provincia.vicenza.it/` — connessione rifiutata.

## 6. Trasporto pubblico (GTFS) — opzionale

- Mobility Database (`mobilitydatabase.org`) e Transitland non raggiungibili, ma il
  **catalogo completo di Mobility Database** è pubblicato anche su Google Cloud Storage
  (`https://storage.googleapis.com/mdb-csv/sources.csv`), letto il 16/10/2026: 3.543
  feed, 77 italiani, **nessuno di SVT o di Vicenza** (l'unico che copre Vicenza è un
  vecchio feed nazionale Trenitalia del 2022, marcato *deprecated*).
- **In uso**: fermate OSM con frequenza per fascia **stimata** in
  `config.yaml -> params.trasporto.frequency_estimate` (bus: giorno 1; sera 0,4; notte
  fonda 0; treno: sera 0,8; notte fonda 0,3). Flag `proxy`.

## 7. Eventi del Comune — opzionale

- **URL**: `https://eventi.comune.vicenza.it/` — connessione rifiutata.
- **In uso**: nessun evento reale. Per la demo esiste uno **scenario simulato** con tre
  eventi inventati in luoghi reali (`data/demo/eventi_demo.csv`), usato solo con
  `--demo` e segnalato nei risultati (`scenario_demo: true`). Gli eventi veri andranno
  in `data/manual/eventi.csv`, con le stesse colonne.

## 8. Punti Viola (DonneXStrada) — opzionale

- Mappa pubblica non raggiungibile. **Non simulati di proposito**: un punto di aiuto
  inventato potrebbe indirizzare una persona in difficoltà verso un luogo che non lo è.
  Se il team ottiene i dati nel rispetto delle condizioni d'uso, basta
  `data/manual/punti_viola.csv` (`lat`, `lon`, eventuale `opening_hours`).

## 9. Open-Meteo e astral

- **astral** (offline): alba e tramonto per Vicenza (45,5455 N, 11,5354 E), fuso
  Europe/Rome. Usato per le fasce orarie.
- **Open-Meteo** (`api.open-meteo.com` e `archive-api.open-meteo.com`, senza chiave,
  dati CC BY 4.0): client implementato in `model/dynamic.py` con cache di 30 minuti.
  Da qui non è raggiungibile: in quel caso il meteo è `sereno` e il risultato lo dichiara
  (`fonte: default (Open-Meteo non raggiungibile)`). L'override manuale
  `sereno`/`pioggia`/`nebbia` funziona sempre.

## 10. Carta Tecnica Regionale (IDT2) — opzionale, fase 6

- `https://idt2.regione.veneto.it/` — connessione rifiutata. Non tentata oltre.

## Overture Maps — Places (fonte aggiunta)

- **URL**: `s3://overturemaps-us-west-2/release/2026-09-23.1/theme=places/` (registro AWS
  Open Data). Letti solo i gruppi di righe che coprono Vicenza (6 su 256 di un file).
- **Licenza**: CDLA-Permissive-2.0 (luoghi da Meta, Microsoft, Foursquare,
  AllThePlaces, BrightQuery).
- **Filtri** (`config.yaml -> sources.overture`): solo categorie con un equivalente nel
  modello (negozi, ristoranti, bar, caffè, farmacie, cinema, teatri, biblioteche,
  ospedali, polizia…); esclusi i luoghi chiusi definitivamente; BrightQuery (registro
  di imprese, spesso sedi legali) solo con confidenza ≥ 0,75; eliminati i doppioni di
  OSM (stessa categoria entro 15 m o nome simile entro 40 m).
- **Risultato**: 4.493 attività aggiunte alle 1.174 di OSM (area comunale + 1 km); 456
  punti di aiuto in più (soprattutto bar e farmacie). Gli orari non ci sono: si usano quelli
  predefiniti per categoria (flag `proxy`).

## Illuminazione pubblica

Nessuna fonte del brief ha dati sulla luce. Ricerca e piano in
[`docs/illuminazione.md`](docs/illuminazione.md) e
[`docs/piano_dati_reali.md`](docs/piano_dati_reali.md). Oggi la luce viene da: `lit` OSM
(11% dei tratti, measured), `lit` di una via adiacente (8%), lampioni OSM (12%) e una
**stima statistica** addestrata sui tratti con `lit` noto (68%, AUC 0,86 in validazione
per quartiere). Ogni tratto porta `fonte_luce`.

## Fonti escluse per scelta (brief)

Dati su reati; il vecchio studio su degrado e furti di biciclette; localizzazioni di
case rifugio o strutture di accoglienza per donne (escluse anche dai punti di aiuto:
`pipeline/pois.py` scarta ogni `social_facility`).
