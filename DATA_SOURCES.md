# Fonti dati

Stato al **16 ottobre 2026** (orari UTC). Ogni tentativo di download viene
registrato dalla pipeline in `data/raw/sources_log.json`.

> **Vincolo di rete.** L'ambiente in cui è stato sviluppato il backend ha una policy
> di rete che **rifiuta le connessioni** (HTTP 403 sul CONNECT) verso quasi tutte le
> fonti del brief: Overpass, Nominatim, SIT, ISTAT, dati.veneto.it, Open-Meteo,
> eventi del Comune, Geoportale della Provincia, Mobility Database, Transitland,
> IDT2. La verifica è stata ripetuta su richiesta, con lo stesso esito. Era raggiungibile
> invece **AWS S3**, da cui è stato preso il planet di OpenStreetMap. Su un'altra
> macchina, o allargando la policy, la pipeline usa le fonti originali
> senza modifiche al codice; in alternativa, ogni fonte si sblocca mettendo i file in
> `data/manual/` (vedi sotto).

## Riepilogo

| # | Fonte | Stato | Usata per | Flag |
|---|---|---|---|---|
| 1 | OpenStreetMap | **usata** (planet AWS, dati al 12/10/2026) | rete pedonale, tutti i parametri da OSM, quartieri | measured / proxy |
| 2 | SIT VI 2.0 (Comune) | non raggiungibile | — (quartieri, PI, punti luce previsti) | — |
| 3 | ISTAT basi territoriali | non raggiungibile | — (residenti) | sostituita da proxy OSM |
| 4 | dati.veneto.it | non raggiungibile | — | — |
| 5 | Geoportale Provincia di Vicenza | non raggiungibile | — | — |
| 6 | GTFS bus urbani | non raggiungibile (Mobility Database, Transitland) | — | frequenza stimata: proxy |
| 7 | Eventi del Comune | non raggiungibile | — | modulo dinamico pronto, nessun evento |
| 8 | Punti Viola (DonneXStrada) | non raggiungibile, nessun file manuale | — | — |
| 9 | Open-Meteo / astral | Open-Meteo non raggiungibile; astral ok (offline) | fasce orarie dal tramonto | — |
| 10 | Carta Tecnica Regionale (IDT2) | non raggiungibile (opzionale, fase 6) | — | — |

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
- **Cosa è stato usato**: confine comunale (relazione `admin_level=8`, `name=Vicenza`);
  rete pedonale con il filtro `walk` di osmnx replicato in Python (`pipeline/osm.py`),
  più una regola italiana: escluse `motorroad=yes` e `highway=trunk` senza marciapiede
  (strade extraurbane principali, vietate ai pedoni dall'art. 175 del Codice della
  strada; disattivabile con `network.italian_road_rule`); lampioni, `lit`, negozi e
  amenity con `opening_hours`, fermate e stazioni con `shelter`, panchine, muri/siepi/
  recinzioni, binari, `landuse`, parchi e `leisure`, edifici, `place`.
- **Copertura** (dettaglio in `reports/osm_coverage.md`): 13.728 tratti, 804 km;
  `lit` sul 12% della lunghezza; 2.835 lampioni; 999 attività di cui solo il 15,7% con
  `opening_hours`; `sidewalk` sull'11% delle strade veicolari; `surface` sul 66%;
  `landuse` sul 74% della superficie comunale; 401 fermate (295 con `shelter`).
- **Problemi**: i negozi mappati sono pochi per una città di 110 mila abitanti (418
  `shop=*`): fronti attivi e presenza di persone sono sottostimati dove OSM è
  incompleto. Il percorso Overpass + osmnx è implementato ma non è stato possibile
  eseguirlo da questo ambiente.

## 2. SIT VI 2.0 — Comune di Vicenza

- **URL**: `https://sit.comune.vicenza.it/` — connessione rifiutata dalla policy di rete
  (16/10/2026 15:35 UTC). Non ho quindi potuto cercare download diretti o WFS.
- **Effetto**: quartieri da OSM (fallback, sotto); zonizzazione del PI non usata (l'uso
  del suolo viene da OSM `landuse`); nessun punto luce.
- **Come sbloccare**: mettere i file in `data/manual/sit/` (shapefile con `.prj`,
  GeoPackage o GeoJSON). La pipeline cerca file con "quart", "circoscr" o "zone" nel
  nome per i quartieri; se manca il `.prj` assume EPSG:3003 e controlla che il centroide
  cada su Vicenza. Per la zonizzazione del PI servirà la legenda dei codici di zona
  (tabella `pi_zone_map` in `config.yaml`, da compilare quando arriva il file).
- **Licenza**: da verificare sul portale.

### Quartieri (fallback)
Il SIT non è raggiungibile e OSM non ha poligoni di quartiere né confini di livello
9/10 per Vicenza. OSM ha però **38 nodi `place=suburb/quarter/neighbourhood`** (Centro
storico, San Pio X, Laghetto, Villaggio del Sole, Ferrovieri, …): i confini sono stati
**approssimati con celle di Voronoi** attorno a questi punti, ritagliate sul confine
comunale. Sono adatti a un primo aggregato, non ai confini amministrativi: vanno
sostituiti con quelli del SIT appena disponibili.

## 3. ISTAT — basi territoriali e popolazione per sezione

- **URL**: `https://www.istat.it/` — connessione rifiutata (16/10/2026 15:35 UTC).
- **Effetto**: la componente "residenti" della presenza di persone usa un **proxy**:
  superficie utile degli edifici residenziali OSM entro 100 m (area × piani, piani
  stimati per tipo di edificio se manca `building:levels`), normalizzata sul
  90° percentile della città. I "residenti esposti" per quartiere non sono calcolabili.
- **Come sbloccare**: mettere in `data/manual/istat/` lo shapefile delle sezioni di
  censimento 2021 (basi territoriali, Veneto) e il CSV delle variabili censuarie con
  la popolazione per sezione; il codice filtra `PRO_COM = 24116` e unisce per codice
  di sezione.
- **Licenza**: Creative Commons Attribuzione (versione da verificare sul sito ISTAT).

## 4. dati.veneto.it — opzionale

- **URL**: `https://dati.veneto.it/api/3/action/package_search?q=vicenza` (API CKAN) —
  connessione rifiutata. Nessun dataset elencato o integrato.

## 5. Geoportale della Provincia di Vicenza — opzionale

- **URL**: `https://geoportale.provincia.vicenza.it/` — connessione rifiutata.

## 6. Trasporto pubblico (GTFS) — opzionale

- **URL**: Mobility Database (`mobilitydatabase.org`) e Transitland (`transit.land`) —
  connessione rifiutata; non è stato possibile verificare se esiste un feed SVT.
- **Fallback in uso**: fermate OSM con frequenza per fascia **stimata** in
  `config.yaml -> params.trasporto.frequency_estimate` (bus: giorno 1; sera 0,4;
  notte fonda 0; treno: sera 0,8; notte fonda 0,3). Flag `proxy`.

## 7. Eventi del Comune — opzionale

- **URL**: `https://eventi.comune.vicenza.it/` — connessione rifiutata. Nessun evento;
  il modulo dinamico (fase 3+) resterà pronto.

## 8. Punti Viola (DonneXStrada) — opzionale

- Mappa pubblica non raggiungibile da qui. Se il team ottiene i dati nel rispetto delle
  condizioni d'uso, basta un `data/manual/punti_viola.csv` con colonne `lat`, `lon` e,
  se noto, `opening_hours`: vengono aggiunti ai punti di aiuto.

## 9. Open-Meteo e astral

- **astral** (libreria offline, nessun download): alba e tramonto per Vicenza
  (45,5455 N, 11,5354 E), fuso Europe/Rome. Usato per le fasce orarie.
- **Open-Meteo** (`api.open-meteo.com`, senza chiave, dati CC BY 4.0) — connessione
  rifiutata. Le combinazioni standard usano `meteo: sereno`; l'override manuale
  `sereno`/`pioggia` sarà disponibile nell'API.

## 10. Carta Tecnica Regionale (IDT2) — opzionale, fase 6

- `https://idt2.regione.veneto.it/` — connessione rifiutata. Non tentata oltre (valore basso).

## Illuminazione pubblica

Nessuna fonte del brief ha dati sulla luce. Ricerca dedicata in
[`docs/illuminazione.md`](docs/illuminazione.md): gestore City Green Light (censimento
dei punti luce non pubblico, da chiedere al referente SIT), PICIL del Comune del 2012
con censimento e classificazione delle strade, compositi satellitari SDGSAT-1 a 10–40 m
del JRC, lampioni rilevati da Mapillary (serve un token). Oggi il parametro Luce usa
`lit` e i lampioni di OSM.

## Altre fonti pubbliche proposte (non ancora integrate)

| Fonte | Cosa aggiungerebbe | Costo |
|---|---|---|
| **Overture Maps — Places** (S3 `overturemaps-us-west-2`, raggiungibile da qui) | Molti più esercizi commerciali di OSM (418 negozi): migliora fronti attivi e presenza di persone. Senza orari: si userebbero quelli predefiniti per categoria (proxy). Licenza CDLA-Permissive-2.0 | basso–medio (GeoParquet filtrabile per riquadro) |
| **SDGSAT-1 / GHSL** (JRC) | Proxy della luce misurato dal satellite su tutta la città | medio |
| **Mapillary** (lampioni rilevati) | Lampioni dove OSM non li ha | basso, serve un token |
| **PICIL 2012** (Comune) | Classificazione illuminotecnica delle strade | dipende dal formato (PDF o vettoriale) |

## Fonti escluse per scelta (brief)

Dati su reati; il vecchio studio su degrado e furti di biciclette; localizzazioni di
case rifugio o strutture di accoglienza per donne (escluse anche dai punti di aiuto:
`pipeline/pois.py` scarta ogni `social_facility`).
