# Fonti dati

Stato al **16 ottobre 2026** (orari UTC), dopo l'apertura della rete dell'ambiente.
Ogni tentativo di download è registrato dalla pipeline in `data/raw/sources_log.json`.
Come passare ai dati reali dove oggi c'è ancora un sostituto:
[`docs/piano_dati_reali.md`](docs/piano_dati_reali.md).

## Riepilogo

| # | Fonte | Stato | Usata per | Flag |
|---|---|---|---|---|
| 1 | OpenStreetMap | **usata** (planet AWS, dati al 12/10/2026); Overpass rifiuta le connessioni da questo ambiente | rete pedonale, quasi tutti i parametri | measured / proxy |
| 2 | SIT VI 2.0 (Comune) | il server rifiuta le connessioni da questo ambiente | — | — |
| 3 | **ISTAT basi territoriali 2021** | **usata** | popolazione per sezione (residenti, residenti esposti), circoscrizioni | proxy (residenti) |
| 4 | **dati.veneto.it** (tabelle del Comune) | **usata** | 22 zone ufficiali, residenti per quartiere, sesso ed età | — |
| 5 | Geoportale Provincia di Vicenza | non indagato oltre (nulla in più rispetto a OSM e ISTAT) | — | — |
| 6 | GTFS bus urbani | nessun feed pubblico per SVT | — | frequenza stimata: proxy |
| 7 | Eventi del Comune | robots.txt vieta le API; il calendario consentito richiede login | solo scenario demo simulato (`--demo`) | — |
| 8 | Punti Viola (DonneXStrada) | nessun elenco pubblico per Vicenza | — | — |
| 9 | Open-Meteo / astral | Open-Meteo raggiungibile ma limite giornaliero superato dall'IP condiviso (429); astral ok | fasce orarie; meteo su richiesta | — |
| 10 | Carta Tecnica Regionale (IDT2) | raggiungibile, opzionale (fase 6) | — | — |
| + | Nominatim | **usata** (1 richiesta/s, cache) | geocodifica di zone senza nodo OSM | — |
| + | Meta / CIESIN HRSL (AWS) | usata come variabile del modello della luce; ripiego per i residenti | — | proxy |
| + | Overture Maps Places (AWS) | **usata** | 4.493 attività in più di OSM, punti di aiuto | proxy (orari predefiniti) |
| + | Stima della luce (modello su dati OSM) | **usata** | luce dove OSM non ha dati (68% dei tratti) | proxy |

## 1. OpenStreetMap — obbligatoria

- **URL usato**: `https://osm-pds.s3.amazonaws.com/planet-latest.osm.pbf` (registro
  AWS Open Data), planet settimanale con **timestamp di replica 2026-10-12T00:00:02Z**.
- **Overpass**: anche con la rete aperta `overpass-api.de` chiude la connessione subito
  dopo l'apertura TLS (probabile blocco degli indirizzi cloud); `overpass.kumi.systems`
  e `overpass.private.coffee` rispondono 500. Da un computer del team funziona: il
  percorso Overpass + osmnx è il primo tentativo della pipeline (provato qui solo con
  risposte simulate, `tests/test_osm_paths.py`).
- **Metodo usato**: planet letto in streaming (`pipeline/planet_stream.py`, 70–80 MB/s) e
  filtrato con `osmium extract` sul riquadro di Vicenza, senza salvarlo su disco;
  risultato 13,7 MB (1,39 milioni di nodi, 211 mila vie). Download 16/10/2026.
- **Licenza**: ODbL 1.0 — © OpenStreetMap contributors.
- **Uso**: confine comunale (relazione 45159), rete pedonale (filtro `walk` di osmnx più
  la regola italiana su `trunk`/`motorroad`), lampioni, `lit`, attività con orari,
  fermate, panchine, muri e siepi, binari, `landuse`, parchi, edifici, `place`.
- **Copertura** (`reports/osm_coverage.md`): 13.728 tratti, 804 km; `lit` sul 12% della
  lunghezza; 2.835 lampioni; 999 attività (16% con orari); `sidewalk` sull'11% delle
  strade veicolari; `landuse` sul 74% della superficie.

## 2. SIT VI 2.0 — Comune di Vicenza

- `https://sit.comune.vicenza.it/`: anche con la rete aperta il server chiude la
  connessione durante l'handshake TLS (come Overpass: blocco lato server degli indirizzi
  esterni o cloud). Da un computer in Italia potrebbe funzionare.
- **Sostituti in uso**: quartieri ufficiali ricostruiti da Comune + ISTAT (sotto);
  zonizzazione del PI sostituita da `landuse` OSM; nessun punto luce.
- **Come sbloccare**: file in `data/manual/sit/` (la pipeline li usa con precedenza).

## 3. ISTAT — basi territoriali 2021

- **URL**: `https://www.istat.it/storage/cartografia/basi_territoriali/2021/R05_21.zip`
  (Veneto, 71 MB, aggiornato il 15/04/2025). Scaricato il 16/10/2026.
- **Licenza**: Creative Commons Attribuzione (ISTAT).
- **Contenuto usato**: le 1.577 sezioni di censimento di Vicenza (`PRO_COM = 24116`) con
  **popolazione 2021** (`POP21`, totale 110.293) e **area sub-comunale** (`COM_ASC1`), che
  corrisponde alle 7 circoscrizioni del Comune: la popolazione per circoscrizione coincide
  con quella del Comune entro il 2,5%.
- **Uso**: componente "residenti" della presenza di persone (residenti entro 100 m,
  ripartiti sull'area di ogni sezione); **residenti nelle sezioni attraversate da tratti
  rossi** per quartiere, come chiede il brief; confini delle circoscrizioni.

## 4. dati.veneto.it — tabelle del Comune di Vicenza

- **API**: CKAN su `https://dati.veneto.it/SpodCkanApi/api/3/` (l'endpoint `/api/3/` della
  radice risponde 404). Esportazioni `datastore/dump/<risorsa>.csv`.
- **Licenza**: indicata per ogni dataset (dati aperti del Comune).
- **Usate**:
  - `zone_amministrative_del_comune_di_vicenza`: le **22 zone (quartieri)** con la loro
    circoscrizione (solo elenco, senza geometria);
  - `residenti_per_quartieri_ed_eta___comune_di_vicenza` (2022–2025): residenti per
    quartiere, classe d'età e sesso; servono a ricostruire i confini (sotto) e a stimare
    **donne e over 60** tra i residenti esposti.
- **Scaricate e utili per dopo**: `famiglie_e_residenti_per_via` (residenti per via, 2025:
  111.027 in 1.008 vie), `piano_degli_interventi` (attributi del PI, senza geometria),
  `aree_di_verde_pubblico` (con flag "recintato" e "custodito", senza geometria),
  `numeri_civici`, `consumi_elettrici_per_illuminazione_pubblica` (totali annui 2013–2019),
  `strade`, `piste_ciclabili`.
- **Altri dataset trovati per l'illuminazione**: solo pali di comuni bellunesi e punti
  luce di Rovigo; **nessun dataset di punti luce per Vicenza**.

### Quartieri (22 zone ufficiali, confini ricostruiti)
Il Comune pubblica l'elenco delle zone con la circoscrizione, non i confini (che sono nel
SIT). Ricostruzione: ogni sezione ISTAT è assegnata a una zona **della propria
circoscrizione**, vicina al punto del quartiere (nodo `place` OSM o via omonima), con pesi
regolati finché la popolazione di ogni zona torna con quella ufficiale 2025. Risultato:
circoscrizioni esatte; popolazione per zona entro l'1,1% (mediana) di quella del Comune,
massimo 17% (Polegge, Capitello, Laghetto). Da sostituire con i confini del SIT appena
disponibili.

## 5. Geoportale della Provincia di Vicenza — opzionale

- Raggiungibile da ora; non indagato oltre perché ISTAT e Comune coprono già confini e
  popolazione.

## 6. Trasporto pubblico (GTFS) — opzionale

- Catalogo Mobility Database (3.543 feed, 77 italiani): nessun feed SVT o Vicenza. Sito
  SVT: solo RSS. Ricerca web: nessun GTFS pubblico.
- Dato utile trovato: di sera il servizio urbano è a chiamata (ChiamaBus) dalle 20:30 alle
  23:30, il sabato fino alle 3:30 ([SVT ChiamaBus](https://apps.apple.com/mt/app/svt-chiamabus/id6474303955)).
- **In uso**: frequenza per fascia stimata in `config.yaml` (bus: sera 0,4, notte fonda 0).

## 7. Eventi del Comune — opzionale

- `https://eventi.comune.vicenza.it/` (piattaforma OpenAgenda): il `robots.txt` **vieta**
  `/api/` (da cui la pagina carica gli eventi) e consente solo
  `/backend/opendata/api/calendar`, che però richiede login. Per rispetto delle condizioni
  d'uso **non vengono scaricati automaticamente**.
- **In uso**: solo lo scenario **simulato** di `data/demo/eventi_demo.csv` (con `--demo`).
- **Come sbloccare**: chiedere al Comune un export (iCal o CSV) o le credenziali del
  calendario; gli eventi veri vanno in `data/manual/eventi.csv`.

## 8. Punti Viola (DonneXStrada) — opzionale

- Nessun elenco pubblico dei Punti Viola di Vicenza trovato. Non simulati di proposito.
  Con un accordo con l'associazione basta `data/manual/punti_viola.csv`.

## 9. Open-Meteo e astral

- **astral** (offline): alba e tramonto, fuso Europe/Rome.
- **Open-Meteo**: raggiungibile, ma l'indirizzo condiviso di questo ambiente ha superato il
  limite giornaliero gratuito (HTTP 429 «Daily API request limit exceeded»). Sui computer
  del team funziona. Senza risposta il meteo è `sereno` e il risultato lo dichiara;
  l'override `sereno`/`pioggia`/`nebbia` funziona sempre.

## 10. Carta Tecnica Regionale (IDT2) — opzionale, fase 6

- Raggiungibile da ora; non integrata (valore basso, fase 6).

## Overture Maps — Places (fonte aggiunta)

- `s3://overturemaps-us-west-2/release/2026-09-23.1/theme=places/`, licenza
  CDLA-Permissive-2.0. Solo categorie con un equivalente nel modello, esclusi i luoghi
  chiusi e le sedi legali (BrightQuery con confidenza < 0,75), senza i doppioni di OSM.
  Risultato: 4.493 attività e 456 punti di aiuto in più; orari predefiniti (proxy).

## Meta / CIESIN HRSL (fonte aggiunta)

- `https://dataforgood-fb-data.s3.amazonaws.com/hrsl-cogs/` (CC BY 4.0), popolazione a
  ~30 m (totale 112.429 nel Comune). Oggi è una variabile del modello della luce e il
  ripiego per i residenti quando ISTAT manca.

## Illuminazione pubblica

Nessuna fonte pubblica ha i punti luce di Vicenza: né dati.veneto.it né il Comune. Il
**PICIL del 2012** (`servizi2.comune.vicenza.it/file/77620-ralazionepicil.pdf`, ora
scaricato e letto) riporta il censimento solo in forma aggregata (per sorgente e potenza,
nell'allegato 3, non pubblicato) e nessun dato per via. Il parametro Luce usa quindi:
`lit` OSM (11% dei tratti), `lit` di una via adiacente (8%), lampioni OSM (12%) e la
**stima statistica** (68%, AUC 0,87 e accuratezza 93% in validazione per quartiere). Ogni
tratto porta `fonte_luce`. Piano per il dato reale: [`docs/piano_dati_reali.md`](docs/piano_dati_reali.md).

## Fonti escluse per scelta (brief)

Dati su reati; il vecchio studio su degrado e furti di biciclette; localizzazioni di case
rifugio o strutture di accoglienza per donne (escluse anche dai punti di aiuto).
