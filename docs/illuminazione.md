# Illuminazione delle strade a Vicenza: cosa esiste e cosa si può usare

Ricerca del 16 ottobre 2026 per il parametro **Luce** (peso 15 su 100 di notte,
il più alto del modello). Nessuna delle fonti elencate nel brief contiene oggi
dati sull'illuminazione: questa nota raccoglie le alternative trovate.

## 1. Cosa usa oggi la pipeline

Ordine di priorità implementato in `pipeline/params.py` (funzione `light`):

| Priorità | Fonte | Valore | Flag | Stato |
|---|---|---|---|---|
| 1 | Punti luce SIT / City Green Light (`data/manual/punti_luce/`) | densità entro 20 m: `min(1, punti / (lunghezza/30))` | measured | **manca**: il codice è pronto, basta mettere il file |
| 2 | Tag OSM `lit` sul tratto | `yes` → 1, `no` → 0, `limited` → 0,5 | measured | 12% della lunghezza della rete |
| 3 | `lit` di una via adiacente (entro 12 m, es. marciapiede mappato a parte) | ereditato | proxy | |
| 4 | Lampioni OSM (`highway=street_lamp`, 2.835 a Vicenza) | `min(1, lampioni entro 20 m / (lunghezza/30))` | proxy | solo dove i lampioni risultano mappati (almeno uno entro 100 m): altrove l'assenza di lampioni in OSM non è un dato |
| 5 | Nessuna | parametro escluso, pesi rinormalizzati | excluded | |

La copertura effettiva per tratto è in `reports/validation.md`.

## 2. Fonti trovate

### City Green Light — gestore dell'illuminazione pubblica (dal 2021)
- Secondo il confronto con Comune e SIT riportato nel brief, l'illuminazione pubblica
  è gestita da City Green Light dal 2021 (sede in via Zampieri 15, Vicenza:
  [scheda aziendale](https://www.aziende.it/city-green-light-s-r-l)).
  Il gruppo opera in oltre 250 comuni con servizi di efficienza energetica e smart city
  ([Intesa Sanpaolo, 2023](https://group.intesasanpaolo.com/it/sala-stampa/comunicati-stampa/2023/09/a-city-green-light-197-milioni-per-progetti-sostenibili-nei-comu)).
- Un gestore di questo tipo tiene un **censimento georeferenziato dei punti luce**
  (con tipo di lampada, potenza, altezza, stato e spesso telegestione), ma non è pubblico.
  Non ho trovato né un dataset aperto né una mappa pubblica per Vicenza.
- **Cosa chiedere** al referente SIT o al Comune: export dei punti luce (anche CSV con
  coordinate, oppure shapefile/GeoPackage) con, se possibile, tipo di sorgente (LED o no),
  potenza, altezza del palo, data di sostituzione, regolazione notturna (dimmerazione:
  incide sulla fascia `notte_fonda`). Il file va in `data/manual/punti_luce/` e la
  pipeline lo usa subito con flag `measured`.

### PICIL di Vicenza (2012)
- Il Comune ha redatto il **Piano dell'Illuminazione per il Contenimento
  dell'Inquinamento Luminoso** previsto dalla LR Veneto 17/2009: stesura maggio 2012,
  revisioni agosto e ottobre 2012, a cura del settore Ambiente con Veneto Stellato e
  AIM Servizi a Rete. La relazione contiene una sezione sul **censimento
  dell'illuminazione pubblica**:
  [relazione PICIL](https://servizi2.comune.vicenza.it/file/77620-ralazionepicil.pdf),
  [testo della LR 17/2009](https://servizi2.comune.vicenza.it/file/77622-1LR172009.pdf).
- Un PICIL di solito contiene anche la **classificazione illuminotecnica delle strade**
  (categorie UNI 11248 / EN 13201), cioè il livello di luce di progetto per ogni via:
  sarebbe un buon proxy per tratto, anche dove manca il censimento dei punti luce.
- Limiti: dati del 2012, prima del passaggio a City Green Light e dei LED; non ho
  verificato se il piano sia stato approvato o aggiornato. Il PDF non è raggiungibile
  da questo ambiente di lavoro (dominio bloccato), quindi non l'ho letto.
- **Cosa chiedere**: le tavole del PICIL in formato vettoriale (classificazione delle
  strade e censimento) al SIT.

### Luci notturne da satellite: SDGSAT-1 (GHSL, Commissione europea)
- Il Joint Research Centre ha pubblicato i primi **compositi annuali di luci notturne
  da SDGSAT-1** a 40 m (RGB) e 10 m (pancromatico), con il metodo open source; uno
  studio copre il Nord Italia (2022–2023, circa 120.000 km² dalle Alpi all'Adriatico)
  ([EU Space](https://eu-space.europa.eu/news/observer-looking-earth-after-dark-how-ghsl-and-sdgsat-1-data-turn-nighttime-lights-better-decisions);
  [Uhl et al., ISPRS 2026](https://isprs-archives.copernicus.org/articles/XLIX-B4-2026/619/2026/)).
- Misura la radianza vista dall'alto (lampioni ma anche insegne, vetrine, fari), non
  i lux sul marciapiede; a 10 m è comunque abbastanza fine per distinguere una via
  illuminata da un parco buio. Uso proposto: valore medio dei pixel lungo il tratto,
  normalizzato sulla città, con flag `proxy`, dove manca `lit`.
- Da verificare: licenza, copertura effettiva di Vicenza e URL di download (JRC Data
  Catalogue / GHSL), che da qui non sono raggiungibili.

### Mapillary — lampioni rilevati dalle foto stradali
- Mapillary estrae dalle immagini stradali oggetti puntuali, **lampioni compresi**,
  posizionati quando un oggetto è visto in almeno tre immagini; si scaricano via API
  in GeoJSON ([Mapillary](https://blog.mapillary.com/update/2019/01/23/updating-maps-with-cameras-42-new-point-features.html),
  [help center](https://help.mapillary.com/hc/en-us/articles/115002332165)).
- Integrerebbe i 2.835 lampioni OSM. Serve un **token gratuito** dell'API Mapillary
  (chiave da fornire) e l'accesso a `graph.mapillary.com`; copertura a Vicenza da verificare.

### Altre
- **VIIRS / NASA Black Marble** (~500 m): troppo grossolano per i tratti, utile solo
  come contesto di quartiere.
- **Mapping in OSM**: esistono precedenti di import comunali di lampioni (es. Cento, 2017)
  e di mapping collettivo (PoliMappers «Facciamo Luce», Milano)
  ([wiki OSM](https://wiki.openstreetmap.org/wiki/PoliMappers/Lightning_Mapping_Milano)).
  Una passeggiata di mappatura durante l'hackathon alzerebbe la copertura di `lit`.
- **Segnalazioni dei cittadini** (fase 5): i tipi `luce_scarsa` e `lampione_guasto`
  aggiornano il parametro con la regola del brief (sezione 8).
- **Misure di lux**: il PDF del team indica la soglia di circa 2 lux minimi; nessuna
  fonte pubblica li misura. Si possono raccogliere con app di luxmetro durante le
  camminate esplorative, come segnalazioni con valore.

## 3. Raccomandazione

1. Chiedere subito al referente SIT l'export dei punti luce di City Green Light
   (anche parziale): è l'unica fonte che rende il parametro `measured` ovunque.
2. In parallelo, chiedere le tavole del PICIL (classificazione delle strade).
3. Se il token è disponibile, aggiungere i lampioni Mapillary come `proxy`.
4. Valutare SDGSAT-1 (GHSL) come proxy uniforme su tutta la città.
