# Validazione del punteggio — Vicenza

*Il punteggio stima la sicurezza percepita a partire dai dati disponibili. Non misura la sicurezza reale di un luogo.*

Dati OSM al 2026-10-12T00:00:02Z (fonte: https://osm-pds.s3.amazonaws.com/planet-latest.osm.pbf). Data di riferimento: 2026-11-18 (feriale), ore di riferimento per fascia: giorno 11:00, sera 20:00, notte_fonda 23:30.

Nei testi si parla di **criticità percepite** e **priorità di intervento**: il punteggio non individua zone pericolose.

## Controlli di coerenza

| controllo | esito | dettaglio |
|---|---|---|
| Di sera le vie pedonali del centro storico hanno S medio più alto delle zone industriali | PASS | vie pedonali del centro storico (entro 600 m da Piazza dei Signori (coordinate fisse)): S = 68.0 su 474 tratti; tratti in aree `landuse=industrial`: S = 37.7 su 178 tratti |
| I sottopassi (e i passaggi coperti o senza uscita) risultano penalizzati | PASS | 1,010 tratti con penalità −30% (75 sottopassi, 91 coperti o passaggi sotto edifici, 864 passaggi pedonali senza uscita): S medio 35.1 contro 56.0 degli altri tratti |
| Di giorno la luce pesa molto meno | PASS | peso luce giorno 2.0% vs sera 15.0%; passare da luce 0 a 1 vale in media 2.9 punti di giorno e 19.0 di sera |
| Il profilo «donna» non alza mai S rispetto al riferimento sullo stesso tratto con luce scarsa | FAIL | 965 tratti con luce < 0,5 di sera: per il profilo donna S scende in 559 e sale in 406 (42%, al massimo di +2.41 punti); variazione media -0.18 punti. Motivo: è una proprietà del modello, non un errore di calcolo. Il profilo donna aumenta anche i pesi di visuale e uso del suolo; dopo la rinormalizzazione perdono peso i parametri non moltiplicati (vie di fuga, fronti attivi, punti di aiuto). Dove questi sono bassi e visuale e uso del suolo alti, S sale di poco anche al buio. Cambiare solo i moltiplicatori non basta: con luce ×2 i tratti restano 210, con luce ×3 202. Per garantire il controllo serve una penalità di buio specifica del profilo: è una decisione del team. Il costo per il navigatore invece cresce sempre (controllo successivo). |
| (aggiuntivo) Sui tratti con luce scarsa il costo per metro del profilo donna non è mai inferiore al riferimento | PASS | costo medio per metro 2.49 (donna, λ = 3) contro 1.74 (riferimento, λ = 1,5); tratti con costo inferiore: 0 |
| Nessun tratto ha S fuori da 0–100 | PASS | 0 valori fuori intervallo su 205,920 |
| Nessun NaN nei punteggi | PASS | 0 valori mancanti in S, affidabilità e costo |

## Copertura dei dati

- Tratti pedonali: 13,728 (804.4 km); tratti con `lit`: 12.1% della lunghezza; lampioni OSM: 2,835; attività con `opening_hours`: 15.7% di 999; strade veicolari con `sidewalk`: 11.4%.
- Dettaglio completo in `reports/osm_coverage.md`; stato delle fonti in `DATA_SOURCES.md`.

### Fonti effettivamente usate

- **Attività** (negozi e locali): 1,174 da OSM + 4,493 da Overture Places (senza doppioni; orari non noti → orari predefiniti per categoria, flag proxy).
- **Punti di aiuto**: 233 da OSM + 456 da Overture.
- **Residenti**: HRSL (Meta/CIESIN HRSL ≈ 30 m al posto delle sezioni ISTAT).
- **Luce**: modello statistico (stima) 9,387 tratti (68%); lampioni OSM (stima) 1,697 tratti (12%); tag OSM lit (misurata) 1,494 tratti (11%); lit di una via adiacente (stima) 1,150 tratti (8%).
  Il modello è addestrato sui 1,494 tratti con `lit` noto (1,356 illuminati, 138 no) e validato per quartiere (GroupKFold per quartiere): AUC 0.859, accuratezza 0.928 contro 0.908 di chi risponde sempre "illuminato", riconosce il 47% dei tratti non illuminati. È una stima: va sostituita con i punti luce reali (`docs/piano_dati_reali.md`).

### Origine dei valori per parametro (fascia sera, % dei tratti)

| parametro | measured % | proxy % | excluded % | valore medio |
|---|---|---|---|---|
| Luce | 10.9 | 89.1 | 0.0 | 0.9 |
| Presenza di persone | 0.0 | 100.0 | 0.0 | 0.2 |
| Fronti attivi | 67.8 | 32.2 | 0.0 | 0.1 |
| Visuale libera | 0.0 | 100.0 | 0.0 | 0.7 |
| Vie di fuga | 100.0 | 0.0 | 0.0 | 0.8 |
| Uso del suolo | 80.5 | 0.0 | 19.5 | 0.7 |
| Episodi segnalati | 0.0 | 0.0 | 100.0 |  |
| Cura e degrado | 0.0 | 0.0 | 100.0 |  |
| Qualità del percorso | 33.0 | 67.0 | 0.0 | 0.7 |
| Composizione della folla | 0.0 | 0.0 | 100.0 |  |
| Punti di aiuto | 30.1 | 69.9 | 0.0 | 0.6 |
| Trasporto e attesa | 6.1 | 93.9 | 0.0 | 0.3 |

## Distribuzione di S per fascia e profilo

| fascia | profilo | media | p10 | mediana | p90 | min | max | % rossi | % verdi |
|---|---|---|---|---|---|---|---|---|---|
| giorno | riferimento | 55.8 | 36.2 | 55.6 | 76.5 | 10.9 | 95.7 | 16.1 | 26.3 |
| giorno | donna | 56.0 | 36.6 | 55.9 | 76.4 | 10.9 | 94.9 | 15.5 | 26.8 |
| giorno | donna+giovani_16_34 | 56.4 | 36.6 | 56.4 | 76.7 | 10.6 | 95.0 | 15.2 | 27.8 |
| giorno | over75 | 57.9 | 39.5 | 57.5 | 77.0 | 14.7 | 96.7 | 10.9 | 30.9 |
| giorno | disabilita | 58.6 | 40.5 | 58.4 | 77.4 | 14.9 | 96.8 | 9.4 | 32.6 |
| sera | riferimento | 54.4 | 35.7 | 55.8 | 69.6 | 6.7 | 93.9 | 15.4 | 20.0 |
| sera | donna | 55.8 | 37.2 | 57.4 | 70.9 | 6.7 | 93.8 | 13.3 | 25.8 |
| sera | donna+giovani_16_34 | 55.5 | 37.0 | 57.1 | 70.5 | 6.6 | 93.1 | 13.5 | 24.5 |
| sera | over75 | 56.4 | 38.5 | 57.7 | 71.3 | 7.6 | 94.7 | 11.9 | 26.2 |
| sera | disabilita | 57.8 | 39.0 | 59.5 | 72.4 | 7.5 | 94.8 | 11.1 | 31.5 |
| notte_fonda | riferimento | 49.7 | 32.8 | 51.3 | 62.9 | 6.3 | 91.2 | 19.2 | 6.0 |
| notte_fonda | donna | 51.2 | 34.3 | 52.8 | 64.7 | 6.3 | 91.3 | 17.2 | 8.8 |
| notte_fonda | donna+giovani_16_34 | 50.6 | 33.9 | 52.1 | 63.9 | 6.2 | 90.2 | 18.0 | 7.3 |
| notte_fonda | over75 | 52.2 | 35.8 | 53.6 | 65.7 | 7.1 | 92.3 | 15.8 | 11.5 |
| notte_fonda | disabilita | 53.6 | 36.3 | 55.5 | 67.0 | 7.0 | 92.6 | 14.6 | 16.5 |

S cambia poco da un profilo all'altro, come previsto dal modello (PDF, esempio di calcolo): i profili spostano peso tra parametri, quindi S cambia solo dove un parametro molto pesato per quel profilo è molto diverso dagli altri. Over 75 e disabilità hanno S medio più alto perché pesano molto la qualità del percorso, che in media è buona. L'effetto principale del profilo è sul **costo per il navigatore** (λ): stesso tratto, costo più alto per chi è più sensibile al rischio.

### Costo medio per metro (C/L) per fascia e profilo

| fascia | riferimento | donna | donna+giovani_16_34 | over75 | disabilita |
|---|---|---|---|---|---|
| giorno | 1.33 | 1.65 | 1.64 | 1.39 | 1.38 |
| sera | 1.34 | 1.64 | 1.65 | 1.41 | 1.38 |
| notte_fonda | 1.40 | 1.76 | 1.78 | 1.47 | 1.45 |

### Affidabilità media per fascia

| fascia | media | min | max |
|---|---|---|---|
| giorno | 0.47 | 0.36 | 0.59 |
| prima_ora_buio | 0.51 | 0.39 | 0.64 |
| sera | 0.54 | 0.41 | 0.69 |
| notte_fonda | 0.54 | 0.41 | 0.68 |
| mattina_buia | 0.56 | 0.42 | 0.69 |

## Affidabilità media e S per quartiere (sera, riferimento)

Residenti stimati (HRSL) che vivono entro 100 m da almeno un tratto rosso, di sera: 57,320 su 112,430 (51%), di cui 30,177 donne e 16,594 over 60. Conta anche tratti rossi molto brevi (passaggi senza uscita): è un indicatore di priorità, non di rischio.

| quartiere | tratti | lunghezza_km | S_medio | pct_lunghezza_rossa | affidabilita_media | residenti_stimati | residenti_esposti | donne_esposte |
|---|---|---|---|---|---|---|---|---|
| Maddalene Vecchie | 44 | 11.75 | 31.40 | 78.10 | 0.57 | 260 | 179 | 93 |
| Gogna | 154 | 19.25 | 33.60 | 70.50 | 0.58 | 907 | 793 | 411 |
| Monte Berico | 246 | 22.63 | 33.70 | 69.90 | 0.58 | 861 | 683 | 353 |
| Lobia | 271 | 20.99 | 36.90 | 50.00 | 0.60 | 225 | 141 | 70 |
| Capitello | 176 | 18.27 | 39.70 | 37.10 | 0.57 | 923 | 346 | 173 |
| Bertesina | 168 | 16.65 | 40.40 | 48.70 | 0.56 | 1134 | 818 | 424 |
| Settecà | 1027 | 65.30 | 41.00 | 42.30 | 0.55 | 1911 | 1661 | 827 |
| Saviabona | 89 | 10.37 | 42.30 | 38.60 | 0.53 | 1064 | 642 | 329 |
| Maddalene | 44 | 5.26 | 42.90 | 41.20 | 0.54 | 626 | 405 | 203 |
| Polegge | 177 | 16.83 | 43.30 | 32.00 | 0.57 | 2079 | 528 | 263 |
| Moracchino | 111 | 6.91 | 43.50 | 25.60 | 0.56 | 685 | 464 | 237 |
| Casale | 756 | 58.86 | 43.80 | 33.40 | 0.54 | 6261 | 3620 | 1849 |
| Pomari | 589 | 38.91 | 45.50 | 31.50 | 0.54 | 2399 | 1262 | 635 |
| Ospedaletto | 138 | 12.02 | 46.40 | 34.00 | 0.56 | 1176 | 401 | 205 |
| Borgo Berga | 410 | 18.36 | 46.80 | 30.80 | 0.54 | 1079 | 748 | 390 |
| Ferrovieri | 477 | 29.56 | 47.00 | 28.80 | 0.51 | 4973 | 2804 | 1443 |
| Bertesinella | 256 | 17.23 | 47.70 | 23.80 | 0.50 | 3300 | 1550 | 786 |
| Anconetta | 154 | 13.20 | 47.70 | 25.00 | 0.54 | 2673 | 919 | 468 |
| Cattane | 369 | 24.06 | 47.80 | 28.90 | 0.56 | 3071 | 1250 | 651 |
| La Stanga | 398 | 26.30 | 47.90 | 33.30 | 0.53 | 3904 | 2289 | 1169 |
| Villaggio del Sole | 470 | 26.20 | 48.80 | 25.40 | 0.54 | 3978 | 2965 | 1510 |
| Laghetto | 439 | 27.28 | 50.80 | 18.30 | 0.58 | 2706 | 1439 | 751 |
| San Pio X | 573 | 32.55 | 56.40 | 10.00 | 0.54 | 8151 | 1821 | 938 |
| San Bortolo | 641 | 28.13 | 57.10 | 10.00 | 0.57 | 6551 | 4022 | 2148 |
| Sant'Andrea | 196 | 10.22 | 57.30 | 7.30 | 0.56 | 3698 | 1706 | 920 |
| San Francesco | 489 | 25.02 | 57.60 | 7.60 | 0.55 | 5976 | 2518 | 1323 |
| Santa Caterina | 249 | 11.75 | 57.80 | 12.20 | 0.53 | 1668 | 1112 | 615 |
| Santa Lucia | 372 | 13.62 | 58.60 | 15.50 | 0.56 | 1970 | 938 | 576 |
| San Paolo | 668 | 32.17 | 59.30 | 8.90 | 0.55 | 6578 | 4063 | 2211 |
| San Felice | 707 | 27.94 | 60.00 | 6.20 | 0.54 | 3563 | 1801 | 956 |
| San Giuseppe | 557 | 21.09 | 60.10 | 6.70 | 0.54 | 3737 | 2922 | 1537 |
| San Lazzaro | 222 | 10.66 | 61.30 | 2.40 | 0.55 | 3979 | 1897 | 958 |
| Araceli | 203 | 10.06 | 62.40 | 1.50 | 0.54 | 3308 | 586 | 316 |
| Stadio | 284 | 11.70 | 63.00 | 3.00 | 0.54 | 3844 | 1905 | 1088 |
| San Biagio | 369 | 17.32 | 63.10 | 7.70 | 0.55 | 3295 | 1853 | 1029 |
| Santa Bertilla | 508 | 20.86 | 63.50 | 1.10 | 0.56 | 6058 | 2017 | 1069 |
| Barche | 288 | 9.02 | 65.80 | 6.30 | 0.56 | 1740 | 1307 | 715 |
| Centro storico | 439 | 16.12 | 66.10 | 6.50 | 0.55 | 2119 | 945 | 538 |

## Le 20 vie con S più alto — giorno (riferimento, vie ≥ 100 m)

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Contra' Piazza del Castello | Centro storico | 134.6 | 94.5 | 91.0 | 0.0 | 0.5 |
| Contra' Frasche del Gambero | Centro storico | 118.0 | 94.5 | 94.5 | 0.0 | 0.5 |
| Corso Antonio Fogazzaro | Centro storico | 196.6 | 93.3 | 92.1 | 0.0 | 0.5 |
| Piazzale Alcide De Gasperi | Centro storico | 200.0 | 93.2 | 89.0 | 0.0 | 0.5 |
| Piazza dei Signori | Centro storico | 164.3 | 93.0 | 92.7 | 0.0 | 0.5 |
| Piazza del Castello | Centro storico | 218.0 | 92.9 | 81.1 | 0.0 | 0.5 |
| Via Cesare Battisti | Centro storico | 123.5 | 92.7 | 92.4 | 0.0 | 0.5 |
| Contra' Vescovado | Centro storico | 124.5 | 92.6 | 88.6 | 0.0 | 0.5 |
| Contra' Motton Pusterla | San Biagio | 127.0 | 92.5 | 92.5 | 0.0 | 0.5 |
| Contra' Fedele Lampertico | Centro storico | 105.8 | 92.2 | 89.5 | 0.0 | 0.5 |
| Piazza delle Biade | Barche | 120.3 | 92.1 | 90.5 | 0.0 | 0.5 |
| Contra' San Francesco Vecchio | Centro storico | 192.1 | 91.3 | 90.4 | 0.0 | 0.5 |
| Corso Antonio Fogazzaro | San Biagio | 432.2 | 90.9 | 42.1 | 0.0 | 0.5 |
| Contra' Porti | San Biagio | 152.9 | 90.7 | 90.7 | 0.0 | 0.5 |
| Contra' Pusterla | San Biagio | 111.7 | 90.1 | 84.9 | 0.0 | 0.5 |
| Corso Andrea Palladio | Centro storico | 626.5 | 89.8 | 59.8 | 0.0 | 0.5 |
| Contra' Santi Apostoli | Barche | 143.3 | 89.6 | 89.6 | 0.0 | 0.4 |
| Stradella dei Munari | San Biagio | 106.3 | 89.4 | 80.3 | 0.0 | 0.5 |
| Contra' Pedemuro San Biagio | San Biagio | 330.0 | 89.3 | 68.7 | 0.0 | 0.5 |
| Contra' Riale | Centro storico | 205.8 | 87.6 | 82.7 | 0.0 | 0.5 |

## Le 20 vie con S più basso (priorità di intervento) — giorno

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Strada della Cresolella | Polegge | 357.1 | 23.9 | 22.0 | 100.0 | 0.5 |
| Strada dell'Acquedotto Romano | Lobia | 224.7 | 24.2 | 24.2 | 100.0 | 0.5 |
| Strada Val di Bugano | Settecà | 882.2 | 25.9 | 22.0 | 98.0 | 0.6 |
| Via delle Due Ferrate | Gogna | 479.9 | 25.9 | 22.6 | 100.0 | 0.5 |
| Strada dei Rocoli | Gogna | 1141.2 | 26.3 | 26.2 | 100.0 | 0.5 |
| Via Alessandro Avogadro Casanova | Monte Berico | 155.2 | 26.5 | 26.5 | 100.0 | 0.6 |
| Via Ferdinando Maria Mantovani | Gogna | 1202.8 | 27.2 | 19.2 | 100.0 | 0.5 |
| Strada di Vallarsa | Moracchino | 243.4 | 27.2 | 27.2 | 100.0 | 0.4 |
| Strada della Commenda | Monte Berico | 925.9 | 27.8 | 19.8 | 100.0 | 0.5 |
| Strada della Pergoletta | Monte Berico | 812.6 | 28.3 | 20.2 | 100.0 | 0.5 |
| Via Battaglione Valtellina | Pomari | 184.4 | 28.5 | 28.5 | 100.0 | 0.4 |
| Strada Biron di Sotto | Cattane | 2094.9 | 28.6 | 22.2 | 100.0 | 0.5 |
| Strada della Porciglia | Monte Berico | 787.9 | 28.8 | 26.4 | 100.0 | 0.5 |
| Strada Maglio di Lobia | Lobia | 310.1 | 29.3 | 25.5 | 100.0 | 0.6 |
| Strada vicinale del Monte Crocetta | Villaggio del Sole | 1342.4 | 29.3 | 20.2 | 94.2 | 0.5 |
| Strada Businello | Settecà | 2752.4 | 29.4 | 24.4 | 100.0 | 0.5 |
| Strada della Colombaretta | Pomari | 742.2 | 29.4 | 28.8 | 100.0 | 0.5 |
| Strada dell'Ospedaletto | Bertesina | 2501.6 | 29.8 | 20.3 | 95.6 | 0.5 |
| Strada Postumia | Anconetta | 861.2 | 30.3 | 23.8 | 100.0 | 0.5 |
| Strada Ambrosini | Villaggio del Sole | 406.8 | 30.5 | 30.5 | 100.0 | 0.5 |

## Le 20 vie con S più alto — sera (riferimento, vie ≥ 100 m)

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Corso Antonio Fogazzaro | Centro storico | 196.6 | 91.5 | 89.8 | 0.0 | 0.6 |
| Piazza delle Biade | Barche | 120.3 | 90.0 | 86.5 | 0.0 | 0.5 |
| Piazza dei Signori | Centro storico | 164.3 | 87.4 | 76.6 | 0.0 | 0.6 |
| Contra' Frasche del Gambero | Centro storico | 118.0 | 86.5 | 86.5 | 0.0 | 0.5 |
| Contra' Porta Padova | Stadio | 155.9 | 85.7 | 82.6 | 0.0 | 0.5 |
| Via Livio Zambeccari | Santa Lucia | 145.9 | 85.7 | 85.7 | 0.0 | 0.5 |
| Contra' Pedemuro San Biagio | San Biagio | 330.0 | 84.4 | 69.3 | 0.0 | 0.6 |
| Contra' Venti Settembre | Santa Lucia | 159.6 | 84.2 | 75.4 | 0.0 | 0.5 |
| Stradella dei Munari | San Biagio | 106.3 | 83.8 | 80.5 | 0.0 | 0.6 |
| Contra' Porti | San Biagio | 152.9 | 83.5 | 83.5 | 0.0 | 0.5 |
| Piazzola Gualdi | Santa Caterina | 123.4 | 83.1 | 78.1 | 0.0 | 0.5 |
| Via Cesare Battisti | Centro storico | 123.5 | 82.8 | 82.3 | 0.0 | 0.6 |
| Contra' Motton Pusterla | San Biagio | 127.0 | 82.4 | 82.4 | 0.0 | 0.5 |
| Corso Santi Felice e Fortunato | San Felice | 827.4 | 81.3 | 57.4 | 0.0 | 0.5 |
| Contra' Oratorio dei Servi | Barche | 143.8 | 81.1 | 77.7 | 0.0 | 0.6 |
| Contra' delle Barche | Barche | 300.0 | 81.0 | 61.9 | 0.0 | 0.5 |
| Contra' Jacopo Cabianca | Barche | 170.6 | 80.7 | 66.1 | 0.0 | 0.6 |
| Contra' Sant'Ambrogio | San Biagio | 106.8 | 80.7 | 80.7 | 0.0 | 0.5 |
| Contra' Piazza del Castello | Centro storico | 134.6 | 80.6 | 72.0 | 0.0 | 0.5 |
| Contra' Santi Apostoli | Barche | 143.3 | 80.5 | 80.5 | 0.0 | 0.5 |

## Le 20 vie con S più basso (priorità di intervento) — sera

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Via Alessandro Avogadro Casanova | Monte Berico | 155.2 | 14.2 | 14.2 | 100.0 | 0.7 |
| Strada della Cresolella | Polegge | 357.1 | 14.9 | 14.0 | 98.9 | 0.6 |
| Via Antonio Vigolo | Monte Berico | 163.4 | 15.9 | 15.9 | 100.0 | 0.6 |
| Strada dell'Acquedotto Romano | Lobia | 224.7 | 17.9 | 17.9 | 100.0 | 0.6 |
| Via dei Capuleti | Pomari | 153.2 | 19.6 | 19.6 | 100.0 | 0.5 |
| Strada di Vallarsa | Moracchino | 243.4 | 19.7 | 19.7 | 100.0 | 0.5 |
| Strada Postumia | Anconetta | 861.2 | 20.2 | 16.3 | 100.0 | 0.6 |
| Strada Val di Bugano | Settecà | 882.2 | 20.3 | 15.8 | 98.0 | 0.7 |
| Strada della Colombaretta | Pomari | 742.2 | 21.2 | 19.6 | 93.5 | 0.6 |
| Strada Maglio di Lobia | Lobia | 310.1 | 21.5 | 18.6 | 100.0 | 0.7 |
| Sentiero Parco Villa Guiccioli | Monte Berico | 424.0 | 21.5 | 12.2 | 100.0 | 0.7 |
| Strada vicinale del Monte Crocetta | Villaggio del Sole | 1342.4 | 23.3 | 15.4 | 94.2 | 0.6 |
| Via delle Due Ferrate | Gogna | 479.9 | 23.8 | 18.9 | 100.0 | 0.6 |
| Strada Businello | Settecà | 2752.4 | 24.5 | 17.8 | 99.7 | 0.6 |
| Via Foscarina | Settecà | 773.6 | 25.8 | 22.2 | 100.0 | 0.6 |
| Via Cresole | Polegge | 254.1 | 26.2 | 17.4 | 96.5 | 0.6 |
| Via Battaglione Valtellina | Pomari | 184.4 | 27.4 | 27.4 | 100.0 | 0.4 |
| Strada di Bertesina | San Pio X | 287.9 | 27.5 | 24.0 | 86.4 | 0.5 |
| Via Divisione Acqui | Cattane | 275.1 | 27.8 | 27.8 | 100.0 | 0.5 |
| Strada Biron di Sotto | Pomari | 173.8 | 28.2 | 28.2 | 100.0 | 0.6 |

## Le 20 vie con S più alto — notte fonda (riferimento, vie ≥ 100 m)

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Piazza dei Signori | Centro storico | 164.3 | 84.6 | 74.0 | 0.0 | 0.6 |
| Piazzola Gualdi | Santa Caterina | 123.4 | 77.1 | 73.9 | 0.0 | 0.5 |
| Corso Antonio Fogazzaro | Centro storico | 196.6 | 76.8 | 72.0 | 0.0 | 0.6 |
| Contra' Santi Apostoli | Barche | 143.3 | 76.0 | 76.0 | 0.0 | 0.5 |
| Contra' Pedemuro San Biagio | San Biagio | 330.0 | 73.9 | 62.6 | 0.0 | 0.6 |
| Via Cesare Battisti | Centro storico | 123.5 | 73.8 | 73.3 | 0.0 | 0.6 |
| Contra' San Faustino | Barche | 202.2 | 72.8 | 71.2 | 0.0 | 0.5 |
| Contra' Motton Pusterla | San Biagio | 127.0 | 72.0 | 72.0 | 0.0 | 0.5 |
| Contra' Santa Maria Nova | San Biagio | 152.8 | 71.9 | 71.9 | 0.0 | 0.5 |
| Stradella dei Munari | San Biagio | 106.3 | 71.8 | 70.5 | 0.0 | 0.6 |
| Contra' Porti | San Biagio | 152.9 | 71.2 | 71.2 | 0.0 | 0.5 |
| Contra' Giuseppe Apolloni | San Biagio | 114.0 | 71.1 | 65.1 | 0.0 | 0.5 |
| Piazza delle Biade | Barche | 120.3 | 70.7 | 62.2 | 0.0 | 0.5 |
| Contra' Piazza del Castello | Centro storico | 134.6 | 70.7 | 60.0 | 0.0 | 0.5 |
| Contra' Mure San Michele | Barche | 153.5 | 70.3 | 70.3 | 0.0 | 0.6 |
| Contra' Porta Padova | Stadio | 155.9 | 69.8 | 66.4 | 0.0 | 0.5 |
| Contra' Venti Settembre | Santa Lucia | 159.6 | 69.8 | 61.4 | 0.0 | 0.5 |
| Stradella dei Cappuccini | San Paolo | 277.0 | 69.7 | 62.7 | 0.0 | 0.5 |
| Contra' Frasche del Gambero | Centro storico | 118.0 | 69.6 | 69.6 | 0.0 | 0.5 |
| Contra' Oratorio dei Servi | Barche | 143.8 | 69.3 | 66.2 | 0.0 | 0.6 |

## Le 20 vie con S più basso (priorità di intervento) — notte fonda

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Strada della Cresolella | Polegge | 357.1 | 13.2 | 12.3 | 98.9 | 0.6 |
| Via Alessandro Avogadro Casanova | Monte Berico | 155.2 | 13.3 | 13.3 | 100.0 | 0.7 |
| Via Antonio Vigolo | Monte Berico | 163.4 | 15.1 | 15.1 | 100.0 | 0.6 |
| Via dei Capuleti | Pomari | 153.2 | 15.5 | 15.5 | 100.0 | 0.5 |
| Strada dell'Acquedotto Romano | Lobia | 224.7 | 17.1 | 17.1 | 100.0 | 0.6 |
| Strada Postumia | Anconetta | 861.2 | 17.9 | 14.8 | 100.0 | 0.6 |
| Strada di Vallarsa | Moracchino | 243.4 | 19.0 | 19.0 | 100.0 | 0.5 |
| Strada Val di Bugano | Settecà | 882.2 | 19.3 | 15.0 | 98.0 | 0.7 |
| Strada della Colombaretta | Pomari | 742.2 | 19.5 | 17.9 | 93.5 | 0.6 |
| Sentiero Parco Villa Guiccioli | Monte Berico | 424.0 | 20.4 | 11.6 | 100.0 | 0.7 |
| Strada Maglio di Lobia | Lobia | 310.1 | 20.4 | 16.6 | 100.0 | 0.7 |
| Strada vicinale del Monte Crocetta | Villaggio del Sole | 1342.4 | 21.2 | 14.7 | 94.2 | 0.6 |
| Strada Businello | Settecà | 2752.4 | 21.7 | 16.5 | 99.7 | 0.6 |
| Via Cresole | Polegge | 254.1 | 22.0 | 13.8 | 100.0 | 0.6 |
| Via Battaglione Valtellina | Pomari | 184.4 | 22.4 | 22.4 | 100.0 | 0.4 |
| Via delle Due Ferrate | Gogna | 479.9 | 22.6 | 18.0 | 100.0 | 0.6 |
| Via Foscarina | Settecà | 773.6 | 24.2 | 20.6 | 100.0 | 0.6 |
| Strada di Bertesina | San Pio X | 287.9 | 24.4 | 20.9 | 100.0 | 0.5 |
| Via Divisione Acqui | Cattane | 275.1 | 25.4 | 25.4 | 100.0 | 0.5 |
| Contra' della Caimpenta | La Stanga | 325.8 | 25.7 | 25.3 | 100.0 | 0.5 |

## Parametri esclusi

Episodi segnalati, cura e degrado, composizione della folla: nessuna fonte pubblica. Sono esclusi e i pesi sono rinormalizzati sugli altri (`unmeasured_strategy: renormalize`). Si attiveranno con le segnalazioni dei cittadini (fase 5).
