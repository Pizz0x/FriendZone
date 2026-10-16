# BRIEF per Claude Code — Backend "Quartieri Vivi" (titolo provvisorio)

Sei lo sviluppatore del **backend iniziale** di un progetto per un hackathon. Il tuo compito è:

1. raccogliere da fonti pubbliche i dati sulle infrastrutture di Vicenza;
2. calcolare un **punteggio di sicurezza percepita stimata** per ogni tratto di strada, poi per ogni via e ogni quartiere;
3. esporre i risultati tramite file e una piccola API;
4. **testare** che tutto funzioni.

L'interfaccia per gli utenti verrà fatta dopo da altri: tu non costruisci frontend, solo una mappa HTML di controllo per verificare i risultati.

Il modello di punteggio è descritto in nel pdf (bozza del team); qui sotto ne trovi la versione corretta da implementare. **Se il PDF e questo brief non coincidono, vale il brief.**

---

## 0. Come devi lavorare

- **Scadenza**: backend funzionante e testato entro **sabato 17 ottobre 2026 alle 09:00**.
- Lavora **per fasi** (sezione 11). Alla fine di ogni fase:
  - esegui il codice e i test;
  - fai un commit git;
  - aggiorna la sezione "Stato" del README con tre elenchi: *funziona*, *stimato*, *da fare*;
  - poi prosegui senza chiedere.

  Chiedimi qualcosa solo se sei bloccato da un file o da una chiave che devo darti io.
- **Non bloccarti su una fonte**: se un download fallisce o una fonte non esiste, registralo in `DATA_SOURCES.md`, usa il fallback e prosegui. La pipeline deve girare anche senza le fonti opzionali.
- **Mai inventare dati.** Nessun dato sintetico in produzione: i dati di prova esistono solo nei test. Ogni valore calcolato porta un flag di origine: `measured` | `proxy` | `excluded`.
- Rispetta robots.txt e condizioni d'uso dei siti; richieste lente; cache su disco di ogni download.
- Stack: Python 3.11. Codice in inglese, documentazione in italiano.

---

## 1. Contesto

- Hackathon **TechWarriors Vicenza 2026** contro la violenza di genere, **sfida 07 – Urbanistica**: rendere spazi pubblici e mobilità più sicuri, accessibili e inclusivi, partendo da come le persone vivono la città, **tenendo distinte le percezioni dai dati sugli episodi segnalati**.
- Il prodotto **parte da un punteggio calcolato solo su fonti pubbliche**. Man mano che le persone lasciano segnalazioni, il punteggio si aggiorna in base al **numero** e al **tipo** delle segnalazioni. Oggi le segnalazioni non ci sono ancora: il modulo va costruito e testato, ma parte vuoto (sezione 8).
- Dal confronto con Comune e SIT:
  - nel database comunale **non esistono dati su sicurezza o aree percepite come pericolose**;
  - i dati SIT VI 2.0 (toponomastica, Piano di Assetto del Territorio, Piano degli Interventi) sono del 2015, considerati affidabili e scaricabili dal portale pubblico;
  - l'illuminazione pubblica è gestita da City Green Light dal 2021; il dataset dei punti luce potrebbe arrivare dal referente SIT, oggi non c'è.
- Utente finale: il Comune (urbanistica, pari opportunità, mobilità) e, in seguito, i cittadini.

---

## 2. Output richiesti

| Output | Contenuto |
|---|---|
| `data/processed/segments.parquet` | Tratti pedonali: id, nome via, classe, lunghezza, quartiere, geometria |
| `data/processed/params.parquet` | Per ogni tratto e fascia oraria: i 12 parametri (valore 0–1 e flag di origine), le penalità, l'affidabilità |
| `exports/segments_{fascia}_{profilo}.geojson` | Tratti con punteggio S, classe di colore e affidabilità, per le combinazioni standard (sez. 6.6) |
| `exports/vie.csv`, `exports/quartieri.csv` | Aggregati per via e per quartiere, per fascia e profilo standard |
| API FastAPI | Sezione 9 |
| `reports/check_map.html` | Mappa di controllo (folium), con selettore di fascia e profilo se possibile, altrimenti una mappa per combinazione standard |
| `reports/validation.md` | Copertura dei dati, distribuzione dei punteggi, migliori e peggiori 20 vie per fascia, controlli di coerenza (sez. 10) |
| `DATA_SOURCES.md` | Per ogni fonte: URL, data di download, licenza, cosa è stato usato, copertura, problemi |

I GeoJSON devono potersi aprire anche in strumenti visuali come kepler.gl o geojson.io: il team non tecnico li userà per controllare i risultati.

---

## 3. Struttura del progetto

```
quartieri-vivi/
  BRIEF.md
  README.md
  DATA_SOURCES.md
  requirements.txt
  config.yaml            # area, pesi, moltiplicatori, soglie, mappature, URL
  docs/modello_punteggio.pdf
  data/raw/              # download (gitignored)
  data/manual/           # file forniti a mano dal team, se servono
  data/processed/
  exports/
  reports/
  pipeline/
    run_all.py           # esegue tutto in ordine, idempotente, con cache
    osm.py
    segments.py
    sources_public.py    # SIT, ISTAT, dati.veneto.it, GTFS, eventi, Punti Viola
    params.py
    aggregate.py         # vie e quartieri
    validate.py          # report e mappa di controllo
  model/
    scoring.py           # pesi, profili, S, penalità, affidabilità
    timebands.py         # fasce dal tramonto
    dynamic.py           # meteo, stagione, eventi
    reports.py           # integrazione delle segnalazioni (sez. 8)
  api/
    main.py              # FastAPI
    db.py                # SQLite per le segnalazioni
  tests/
```

`requirements.txt` di partenza: `osmnx geopandas shapely pyproj networkx numpy pandas pyarrow astral requests geopy fastapi uvicorn pydantic pyyaml folium pytest httpx`. Controlla la versione di osmnx: la 2.x ha cambiato alcuni nomi di funzione.

---

## 4. Area e unità di analisi

- **Area**: l'intero Comune di Vicenza (confine amministrativo da OSM o dal SIT).
- **Tratto**: un arco della rete pedonale OSM tra due incroci, in un grafo non orientato (unisci u→v e v→u). È l'unità di calcolo, perché le vie di fuga e i percorsi dipendono dalla rete.
- **Via**: aggregazione dei tratti con lo stesso nome dentro lo stesso quartiere. I tratti senza nome (sentieri, passaggi) restano tratti singoli con etichetta "percorso senza nome".
- **Quartiere**: confini dal SIT se disponibili. Altrimenti da OSM (`place=suburb/quarter/neighbourhood` oppure `admin_level` 10). Altrimenti dalle sezioni di censimento ISTAT. Come ultima scelta, una griglia esagonale.
- Calcoli metrici in EPSG:32632, export in EPSG:4326.

---

## 5. Fonti dati

Lavora in quest'ordine. Le fonti marcate *opzionale* hanno un tempo massimo: se non funzionano entro quel limite, registra il problema e passa oltre.

| # | Fonte | Cosa usare | Note |
|---|---|---|---|
| 1 | **OpenStreetMap** (Overpass via osmnx) — obbligatoria | Rete pedonale (`network_type="walk"`). `highway=street_lamp`; `lit` sulle vie; `shop=*`; `amenity` bar, cafe, restaurant, pub, fast_food, ice_cream, pharmacy, cinema, theatre, library, police, hospital, clinic, nightclub, con `opening_hours`; `highway=bus_stop`, `public_transport=platform`, `railway=station`, con `shelter` e `lit`; `tunnel=yes`, `covered=yes`, `layer<0` su footway/path/cycleway; `highway=steps`; `barrier=wall/hedge/fence`; `landuse=*`; `leisure=park/garden/playground/pitch/fitness_station` con `opening_hours`; `sidewalk=*`, `footway=sidewalk/crossing`, `surface`, `wheelchair`, `kerb`; `amenity=bench` | Se Overpass è lento, cambia endpoint. Scrivi un report di copertura: % di tratti con `lit`, numero di lampioni, % di POI con `opening_hours`, % di tratti con `sidewalk`. Più è bassa la copertura, più i parametri saranno `proxy` o `excluded` |
| 2 | **SIT VI 2.0** — Comune di Vicenza (portale `sit.comune.vicenza.it`) | Confini di quartieri e circoscrizioni; zonizzazione del Piano degli Interventi; verde pubblico; servizi; eventuali strati di illuminazione | Cerca un download diretto o un servizio WFS. Se non è scaricabile in modo automatico entro 30 minuti, chiedimi di metterlo in `data/manual/sit/`. Sistema di riferimento: leggi il `.prj`; se manca prova EPSG:3003 e verifica che il centroide cada su Vicenza confrontandolo con OSM. Per i codici di zona del PI crea in config una tabella `pi_zone_map` (misto, residenziale, produttivo, verde pubblico, servizi, vuoto) e chiedimi la legenda se non è deducibile |
| 3 | **ISTAT, basi territoriali** | Sezioni di censimento del Comune di Vicenza (codice da verificare: PRO_COM 24116) con popolazione per sezione | Serve per la densità di residenti (proxy "persone") e per i residenti esposti. Verifica quale anno è disponibile |
| 4 | **dati.veneto.it** — opzionale, max 30 min | Usa l'API di ricerca del portale (se è CKAN: `package_search`) con parole come vicenza, illuminazione, aree verdi, piste ciclabili, parcheggi, attività commerciali | Elenca in `DATA_SOURCES.md` i dataset trovati. Integra solo quelli georeferenziati o facilmente georeferenziabili |
| 5 | **Geoportale Provincia di Vicenza** — opzionale, max 20 min | Strati WMS/WFS utili (viabilità, servizi) | Usali solo se aggiungono qualcosa rispetto a OSM e SIT |
| 6 | **Trasporto pubblico (GTFS)** — opzionale, max 20 min | Cerca un feed GTFS dei bus urbani di Vicenza su Mobility Database o Transitland. Se esiste: frequenza e ultima corsa per fermata e fascia | Fallback: fermate OSM con frequenza serale stimata in config (flag `proxy`) |
| 7 | **Eventi del Comune** — opzionale, max 30 min | Il portale eventi del Comune (`eventi.comune.vicenza.it`, agenda "Viva") ha anche una sezione Luoghi con indirizzi. Verifica se esiste un feed (RSS, iCal, JSON, dati strutturati nella pagina). Se sì: titolo, date, orari, luogo; geocodifica gli indirizzi con Nominatim (1 richiesta al secondo, user-agent dedicato, cache) | Fallback: nessun evento; il modulo dinamico resta pronto |
| 8 | **Punti Viola (DonneXStrada)** — opzionale, max 15 min | Esercizi formati per accogliere chi è in pericolo; c'è una mappa pubblica | Usali solo se i dati sono accessibili nel rispetto delle condizioni d'uso; altrimenti, se esiste, leggi `data/manual/punti_viola.csv` |
| 9 | **Open-Meteo** (senza chiave) e **astral** (offline) | Pioggia e visibilità; alba e tramonto per Vicenza, fuso Europe/Rome | Servono per il calcolo dinamico (sez. 7) |
| 10 | **Regione Veneto, geoportale IDT2 (Carta Tecnica Regionale)** — opzionale, solo a fine lavoro, max 45 min | Marciapiedi o ingombri stradali, se esistono come poligoni utili | Valore basso: il parametro "qualità del percorso" pesa poco. Fallo solo se tutto il resto è completo |

**Non usare**: dati su reati; il vecchio studio su degrado e furti di biciclette; localizzazioni di case rifugio o strutture di accoglienza per donne (mai, nemmeno come punti di aiuto).

Se trovi **altre fonti pubbliche utili** non elencate, proponile in `DATA_SOURCES.md` con una riga su cosa aggiungerebbero, e integrale solo se il costo è basso.

---

## 6. Modello di punteggio

### 6.1 Fasce orarie (calcolate dal tramonto di quel giorno a Vicenza)

| Fascia | Intervallo | Pesi |
|---|---|---|
| `giorno` | dall'alba a 30 minuti prima del tramonto | giorno |
| `prima_ora_buio` | da 30 minuti prima a 60 minuti dopo il tramonto (corregge un buco di 30 minuti presente nel PDF) | media 50/50 giorno e notte |
| `sera` | dalla fine della prima ora di buio alle 22:30 | notte |
| `notte_fonda` | dalle 22:30 alle 05:00 | notte, con peso di "persone" ×1,3 poi rinormalizzato |
| `mattina_buia` | dalle 05:00 all'alba, solo se l'alba è dopo le 05:00 | notte |

Considera anche `feriale` e `weekend`, che influisce sul proxy "persone" nelle zone con locali.

### 6.2 I 12 parametri (valori da 0 = pessimo a 1 = ottimo, per tratto e fascia)

| # | Parametro | Peso notte | Peso giorno | Calcolo da fonti pubbliche | Flag |
|---|---|---|---|---|---|
| 1 | Luce | 15 | 2 | Se ci sono punti luce dal SIT, usali: densità entro 20 m. Altrimenti `lit=yes`→1, `lit=no`→0. Altrimenti `street_lamp` OSM: `min(1, lampioni / (lunghezza/30))`. Altrimenti escluso | measured / proxy / excluded |
| 2 | Presenza di persone | 14 | 12 | Combinazione normalizzata di: attività aperte in quell'ora entro 50 m, fermate entro 100 m, densità di residenti ISTAT, eventi attivi se disponibili. Parchi da ottobre ad aprile ×0,6. Pioggia ×0,7 | proxy |
| 3 | Fronti attivi | 12 | 10 | POI aperti in quell'ora entro 25 m, per 100 m di tratto; 6 o più per 100 m = 1. Interpreta `opening_hours`; se l'orario manca, usa orari predefiniti per categoria in config (negozi lun-sab 9–19:30, bar 7–24, ristoranti 12–15 e 19–23, farmacie 8:30–19:30 salvo `24/7`) | measured / proxy |
| 4 | Visuale libera | 10 | 10 | Parti da 0,7; abbassa con muri e siepi entro 5 m, tratti coperti, sottopassi, binari adiacenti. Pioggia ×0,8 | proxy |
| 5 | Vie di fuga | 10 | 8 | Dal grafo: incroci ogni 100 m; vicolo cieco (un estremo con grado 1) → 0,2; tratti oltre 200 m senza incroci penalizzati; scale | measured |
| 6 | Uso del suolo | 9 | 6 | `landuse` entro 30 m: residenziale/commerciale/misto 1; industriale, ferrovia, cantiere, dismesso 0; parco 0,5 di giorno e 0,3 di notte. La zonizzazione del PI, se c'è, ha la priorità | measured |
| 7 | Episodi segnalati | 8 | 12 | Nessuna fonte pubblica → **escluso** finché non arrivano segnalazioni (sez. 8) | excluded |
| 8 | Cura e degrado | 7 | 12 | Nessuna fonte pubblica → **escluso** finché non arrivano segnalazioni | excluded |
| 9 | Qualità del percorso | 5 | 14 | pedestrian/footway/living_street 1; residenziale con `sidewalk=both` 0,9; primaria o secondaria con `sidewalk=no` 0,2; senza tag, valore per classe di strada; superficie sconnessa −0,2; scale 0,3; bonus panchine | measured / proxy |
| 10 | Composizione della folla | 4 | 6 | Non misurabile da fonti pubbliche → escluso | excluded |
| 11 | Punti di aiuto | 3 | 4 | Distanza dal punto di aiuto più vicino aperto in quell'ora (farmacia, bar, Punto Viola, polizia, ospedale): 0 m → 1, 400 m o più → 0 | measured |
| 12 | Trasporto e attesa | 3 | 4 | Distanza dalla fermata: 150 m o meno → 1, 600 m o più → 0. Moltiplica per un bonus se c'è pensilina o luce, e per la frequenza serale (GTFS oppure stima) | measured / proxy |

**Penalità bloccanti**, moltiplicative:
- sottopasso, tratto coperto o passaggio senza uscita: −30%;
- tratto dentro un parco nelle fasce di buio, se il parco è chiuso secondo `opening_hours` o non illuminato: −40%.

**Parametri esclusi**: rinormalizza i pesi su quelli disponibili (`unmeasured_strategy: renormalize`, default). In config prevedi l'alternativa `neutral`, che assegna 0,5.

**Affidabilità** di ogni tratto = Σ(peso base × fattore) / 100, con fattore 1 se `measured`, 0,5 se `proxy`, 0 se `excluded`. Va sempre esportata accanto al punteggio: con i soli dati pubblici sarà bassa per alcuni parametri, ed è giusto che si veda.

### 6.3 Profili

Selezione multipla e combinabile: i moltiplicatori si moltiplicano tra loro, poi si rinormalizzano i pesi. λ di base = 1,5.

| Profilo | Moltiplicatori dei pesi | λ |
|---|---|---|
| Riferimento (neutro / uomo adulto) | nessuno | 1,5 |
| Donna | luce ×1,3; persone ×1,2; visuale ×1,3; uso suolo ×1,3; episodi ×1,4; folla ×1,6 | ×2 |
| 16–34 anni | trasporto ×1,4; episodi ×1,2 | invariata |
| Over 75 | percorso ×2,5; luce ×1,2; punti di aiuto ×1,5 | ×1,3 |
| Disabilità motoria o visiva | percorso ×2,5; luce ×1,3; vie di fuga ×1,3 | ×1,3 |
| LGBTQ+ | episodi ×1,5; folla ×1,3 | ×1,3 |
| Molestie subite di recente | episodi ×1,5 | ×1,3 |
| Conosce bene la zona | nessuno | ×0,8 |
| In compagnia | nessuno | ×0,5 |

Tutti i valori stanno in `config.yaml`, così il team può cambiarli senza toccare il codice.

### 6.4 Formule

- Pesi personalizzati: `w_i = b_i(t) · Π m_{i,g} / Σ_j b_j(t) · Π m_{j,g}`
- Punteggio del tratto: `S = 100 · Σ w_i · x_i · Π (1 − P_k)`
- Costo per il percorso: `C = L · (1 + λ · ((100 − S)/100)²)`
- Classi: sotto 40 rossa, da 40 a 65 gialla, sopra 65 verde.

### 6.5 Aggregati

- **Via**: media di S pesata sulla lunghezza; S minimo; percentuale di lunghezza rossa; affidabilità media.
- **Quartiere**: media pesata sulla lunghezza; percentuale di lunghezza rossa; le 5 vie peggiori; affidabilità media; residenti nelle sezioni attraversate da tratti rossi, se c'è ISTAT.

### 6.6 Combinazioni standard da precalcolare ed esportare

- Fasce: `giorno`, `sera`, `notte_fonda`.
- Profili: riferimento, donna, donna + 16–34, over 75, disabilità.
- Data di riferimento: un giorno feriale di metà novembre, configurabile.

Qualsiasi altra combinazione si calcola al volo dall'API.

### 6.7 Test obbligatori (`tests/test_scoring.py`)

Riproduci l'esempio del PDF: fascia `sera`, profilo riferimento, tutti i parametri misurati, nessuna rinormalizzazione. Valori x nell'ordine dei 12 parametri:

- A: 0,8 0,7 0,7 0,8 0,9 0,9 0,8 0,8 0,9 0,7 0,8 0,6, nessuna penalità → **S ≈ 79**, costo per metro ≈ **1,07**
- B: 0,5 0,3 0,2 0,5 0,6 0,4 0,3 0,5 0,7 0,2 0,5 0,7, nessuna penalità → **S ≈ 42**, costo ≈ **1,50**
- C: 0,4 0,2 0,1 0,3 0,3 0,5 0,4 0,6 0,5 0,3 0,3 0,3, penalità 30% → **S ≈ 23**, costo ≈ **1,88**
- C lungo 200 m, profilo donna + over 75 (λ = 3,9) → costo ≈ **646 m**, tolleranza ±2%

Aggiungi anche: rinormalizzazione con parametri esclusi; confini delle fasce in un giorno di dicembre e in uno di giugno; combinazione di più profili; calcolo dell'affidabilità.

---

## 7. Calcolo dinamico

`model/dynamic.py` riceve una data e ora e restituisce i parametri modificati:
- fascia dal tramonto (astral);
- feriale o weekend;
- stagione (parchi);
- meteo da Open-Meteo, con cache di 30 minuti e override manuale `sereno`/`pioggia`;
- eventi attivi, se la fonte esiste: effetto da un'ora prima a un'ora dopo l'evento, entro 300 m. Persone +0,3, fronti attivi +0,2, punti di aiuto +0,2, con massimo 1.

---

## 8. Segnalazioni dei cittadini (modulo pronto, oggi vuoto)

Il punteggio parte dai dati pubblici e si aggiorna con le segnalazioni, in base al loro **numero** e al loro **tipo**. Costruisci il modulo e testalo con segnalazioni di prova **solo dentro i test**.

### Struttura di una segnalazione
`id, timestamp, lat, lon (oppure segment_id), fascia (giorno/sera/notte), tipo, voto_sicurezza (1–5, facoltativo), genere (facoltativo), fascia_eta (facoltativa)`.

Nessun testo libero salvato in questa fase. Nessun dato identificativo.

### Tipi e parametro su cui agiscono

| Tipo | Parametro | Valore implicito | Emivita |
|---|---|---|---|
| `luce_scarsa` | 1 Luce | 0,2 | 180 giorni |
| `lampione_guasto` | 1 Luce | 0,0 | 30 giorni |
| `poca_gente` | 2 Persone | 0,2 | 180 giorni |
| `angoli_ciechi` | 4 Visuale | 0,2 | 365 giorni |
| `luogo_isolato` | 5 Vie di fuga | 0,3 | 365 giorni |
| `molestie` | 7 Episodi | 0,0 | 365 giorni |
| `degrado` | 8 Cura | 0,2 | 90 giorni |
| `marciapiede_ostacoli` | 9 Percorso | 0,2 | 180 giorni |
| `attesa_mezzi` | 12 Trasporto | 0,2 | 180 giorni |
| `luogo_positivo` | parametri 2, 3, 8 | 0,9 | 180 giorni |

Tutti i valori stanno in `config.yaml`.

### Regola di aggiornamento per parametro (per tratto e fascia)
- `x_aggiornato = (k · x_pubblico + Σ w_r · x_r) / (k + Σ w_r)`
- `w_r` è il peso della segnalazione, ridotto nel tempo secondo l'emivita.
- `k` è la forza del dato pubblico: 5 se `measured`, 2 se `proxy`, 0 se `excluded`. Così le segnalazioni "accendono" i parametri oggi esclusi, come episodi e degrado, e l'affidabilità sale.
- Una segnalazione influisce sui tratti entro 50 m dal punto segnalato.

### Privacy e protezione dagli abusi
Un tratto viene modificato **solo con almeno 5 segnalazioni** dello stesso tipo nella stessa fascia (soglia configurabile; per `lampione_guasto` può essere 2). Le segnalazioni sotto soglia si salvano ma non hanno effetto visibile. Prevedi un campo per un hash anonimo di sessione e un limite di segnalazioni per sessione al giorno: oggi resta un TODO documentato.

### Percezione separata
Il voto di sicurezza 1–5 **non** entra nei 12 parametri. Calcola a parte `S_percepito = (media − 1) / 4 · 100`, per tratto, fascia e gruppo (tutti, donne, over 75), solo con almeno 5 voti. L'API restituisce sempre separati:
- `S_infrastruttura`: dati pubblici più segnalazioni di tipo;
- `S_percepito`;
- il loro divario.

È la distinzione che la sfida chiede in modo esplicito.

### Simulazione per la presentazione
Uno script `simulate_reports.py` aggiunge N segnalazioni di prova su un tratto scelto, **in un database separato** marcato come simulazione. Stampa il prima e dopo di parametri, S e affidabilità. Serve a mostrare come il punteggio evolve; non deve mai toccare il database reale.

---

## 9. API (FastAPI)

| Metodo | Endpoint | Cosa restituisce |
|---|---|---|
| GET | `/health` | stato e data dell'ultimo aggiornamento dei dati |
| GET | `/meta` | pesi, profili, fasce, fonti con date, copertura |
| GET | `/segments?datetime=&profilo=&bbox=&meteo=` | GeoJSON dei tratti con S, classe, affidabilità (con `detail=true` anche i 12 parametri e i flag) |
| GET | `/segments/{id}?datetime=&profilo=` | scomposizione completa: parametri, flag, pesi del profilo, penalità, S_infrastruttura, S_percepito o "n/5", segnalazioni aggregate |
| GET | `/vie?datetime=&profilo=&quartiere=` | aggregati per via |
| GET | `/quartieri?datetime=&profilo=` | aggregati per quartiere |
| POST | `/reports` | valida e salva una segnalazione in SQLite. Risponde "ricevuta", senza dire se ha già effetto |
| GET | `/reports/stats` | solo conteggi aggregati sopra soglia |

Se `datetime` manca, si usa l'ora attuale nel fuso Europe/Rome. Le combinazioni standard vengono servite dai file precalcolati; le altre sono calcolate in numpy vettoriale con cache. Scrivi test dell'API con il client di test di FastAPI.

---

## 10. Validazione (`reports/validation.md` e `reports/check_map.html`)

- Copertura per fonte e per parametro; percentuale di tratti per flag.
- Distribuzione di S per fascia e profilo; affidabilità media per quartiere.
- Le 20 vie migliori e le 20 peggiori di sera, per controllo a vista da parte del team.
- **Controlli di coerenza**, con esito PASS o FAIL:
  - di sera le vie pedonali del centro storico hanno in media S più alto delle zone industriali;
  - i sottopassi risultano penalizzati;
  - di giorno la luce pesa molto meno;
  - il profilo "donna" non alza mai S rispetto al riferimento sullo stesso tratto con luce scarsa;
  - nessun tratto ha S fuori da 0–100;
  - nessun NaN.
- Mappa folium dei tratti colorati, con tooltip: via, S, affidabilità, i 3 parametri peggiori.

Nei testi usa sempre "criticità percepite" o "priorità di intervento", mai "zone pericolose". In testa al report scrivi: *"Il punteggio stima la sicurezza percepita a partire dai dati disponibili. Non misura la sicurezza reale di un luogo."*

---

## 11. Fasi

| Fase | Tempo indicativo | Contenuto | Fatto quando |
|---|---|---|---|
| 0 | 30 min | Repo, `config.yaml`, `scoring.py` e `timebands.py` con i test | `pytest` passa, inclusi i valori dell'esempio del PDF |
| 1 | 1,5 h | Download OSM di tutta Vicenza, tratti, quartieri (fallback OSM), report di copertura | `segments.parquet` creato; prima mappa di controllo; `DATA_SOURCES.md` compilato |
| 2 | 2 h | I 12 parametri per fascia, penalità, affidabilità, S, aggregati per via e quartiere, export | GeoJSON e CSV generati; `validation.md` con controlli di coerenza tutti PASS, oppure FAIL motivati |
| 3 | 2 h | Fonti pubbliche aggiuntive (5.2–5.8) con i tempi massimi indicati | Ogni fonte integrata o documentata come non disponibile; punteggi ricalcolati |
| 4 | 1 h | API con i suoi test | Tutti gli endpoint rispondono; i test dell'API passano |
| 5 | 1,5 h | Modulo segnalazioni, S_percepito, simulazione | I test dimostrano: nessun effetto sotto soglia; effetto sopra soglia; decadimento nel tempo; parametri esclusi che si attivano; affidabilità che sale |
| 6 | opzionale | Carta Tecnica Regionale; metrica "metri di deviazione imposti" (percorso più breve contro percorso a costo minimo per origini e destinazioni campione) | Solo se tutto il resto è completo |

Alla fine scrivi nel README: come installare, come lanciare `python -m pipeline.run_all`, come avviare l'API con `uvicorn api.main:app`, come aprire la mappa di controllo, e lo **Stato**.
