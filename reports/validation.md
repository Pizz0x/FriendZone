# Validazione del punteggio — Vicenza

*Il punteggio stima la sicurezza percepita a partire dai dati disponibili. Non misura la sicurezza reale di un luogo.*

Dati OSM al 2026-10-12T00:00:02Z (fonte: https://osm-pds.s3.amazonaws.com/planet-latest.osm.pbf). Data di riferimento: 2026-11-18 (feriale), ore di riferimento per fascia: giorno 11:00, sera 20:00, notte_fonda 23:30.

Nei testi si parla di **criticità percepite** e **priorità di intervento**: il punteggio non individua zone pericolose.

## Controlli di coerenza

| controllo | esito | dettaglio |
|---|---|---|
| Di sera le vie pedonali del centro storico hanno S medio più alto delle zone industriali | PASS | vie pedonali del centro storico (entro 600 m da Piazza dei Signori (coordinate fisse)): S = 64.0 su 474 tratti; tratti in aree `landuse=industrial`: S = 33.6 su 178 tratti |
| I sottopassi (e i passaggi coperti o senza uscita) risultano penalizzati | PASS | 1,010 tratti con penalità −30% (75 sottopassi, 91 coperti o passaggi sotto edifici, 864 passaggi pedonali senza uscita): S medio 32.9 contro 52.5 degli altri tratti |
| Di giorno la luce pesa molto meno | PASS | peso luce giorno 2.0% vs sera 15.0%; passare da luce 0 a 1 vale in media 2.9 punti di giorno e 19.0 di sera |
| Il profilo «donna» non alza mai S rispetto al riferimento sullo stesso tratto con luce scarsa | PASS | 965 tratti con luce < 0,5 di sera: per il profilo donna S scende in 965 e sale in 0 (0%, al massimo di -1.64 punti); variazione media -6.46 punti. |
| (aggiuntivo) Sui tratti con luce scarsa il costo per metro del profilo donna non è mai inferiore al riferimento | PASS | costo medio per metro 3.05 (donna, λ = 3) contro 1.88 (riferimento, λ = 1,5); tratti con costo inferiore: 0 |
| Nessun tratto ha S fuori da 0–100 | PASS | 0 valori fuori intervallo su 205,920 |
| Nessun NaN nei punteggi | PASS | 0 valori mancanti in S, affidabilità e costo |

## Copertura dei dati

- Tratti pedonali: 13,728 (804.4 km); tratti con `lit`: 12.1% della lunghezza; lampioni OSM: 2,835; attività con `opening_hours`: 15.7% di 999; strade veicolari con `sidewalk`: 11.4%.
- Dettaglio completo in `reports/osm_coverage.md`; stato delle fonti in `DATA_SOURCES.md`.

### Fonti effettivamente usate

- **Attività** (negozi e locali): 1,174 da OSM + 4,493 da Overture Places (senza doppioni; orari non noti → orari predefiniti per categoria, flag proxy).
- **Punti di aiuto**: 233 da OSM + 456 da Overture.
- **Residenti**: ISTAT 2021 (sezioni di censimento).
- **Luce**: modello statistico (stima) 9,387 tratti (68%); lampioni OSM (stima) 1,697 tratti (12%); tag OSM lit (misurata) 1,494 tratti (11%); lit di una via adiacente (stima) 1,150 tratti (8%).
  Il modello è addestrato sui 1,494 tratti con `lit` noto (1,356 illuminati, 138 no) e validato per quartiere (GroupKFold per quartiere): AUC 0.874, accuratezza 0.93 contro 0.908 di chi risponde sempre "illuminato", riconosce il 41% dei tratti non illuminati. È una stima: va sostituita con i punti luce reali (`docs/piano_dati_reali.md`).

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
| giorno | riferimento | 55.7 | 36.2 | 55.5 | 76.4 | 10.8 | 95.7 | 16.1 | 25.9 |
| giorno | donna | 55.9 | 36.4 | 55.9 | 76.3 | 10.8 | 94.9 | 15.6 | 26.2 |
| giorno | donna+giovani_16_34 | 56.3 | 36.6 | 56.4 | 76.6 | 10.6 | 95.0 | 15.3 | 27.3 |
| giorno | over75 | 57.8 | 39.5 | 57.4 | 77.0 | 14.7 | 96.7 | 10.9 | 30.7 |
| giorno | disabilita | 58.6 | 40.4 | 58.3 | 77.4 | 14.9 | 96.8 | 9.5 | 32.4 |
| sera | riferimento | 51.1 | 32.5 | 52.7 | 65.9 | 5.0 | 89.1 | 18.9 | 11.1 |
| sera | donna | 49.0 | 30.1 | 51.1 | 63.6 | 3.4 | 84.2 | 21.7 | 8.3 |
| sera | donna+giovani_16_34 | 48.8 | 30.0 | 50.8 | 63.2 | 3.3 | 83.6 | 21.9 | 7.9 |
| sera | over75 | 51.9 | 33.9 | 53.6 | 66.5 | 5.1 | 88.4 | 17.5 | 13.2 |
| sera | disabilita | 53.1 | 34.4 | 55.3 | 67.6 | 5.0 | 88.5 | 16.8 | 16.2 |
| notte_fonda | riferimento | 46.7 | 29.8 | 48.4 | 59.7 | 4.8 | 86.4 | 24.4 | 3.6 |
| notte_fonda | donna | 45.0 | 27.6 | 47.1 | 58.1 | 3.2 | 81.8 | 28.1 | 2.2 |
| notte_fonda | donna+giovani_16_34 | 44.4 | 27.3 | 46.5 | 57.4 | 3.1 | 80.9 | 29.5 | 1.9 |
| notte_fonda | over75 | 48.0 | 31.6 | 49.8 | 61.3 | 4.8 | 86.1 | 22.0 | 4.1 |
| notte_fonda | disabilita | 49.4 | 32.1 | 51.5 | 62.5 | 4.7 | 86.3 | 20.2 | 5.1 |

S cambia poco da un profilo all'altro, come previsto dal modello (PDF, esempio di calcolo): i profili spostano peso tra parametri, quindi S cambia solo dove un parametro molto pesato per quel profilo è molto diverso dagli altri. Over 75 e disabilità hanno S medio più alto perché pesano molto la qualità del percorso, che in media è buona. L'effetto principale del profilo è sul **costo per il navigatore** (λ): stesso tratto, costo più alto per chi è più sensibile al rischio.

### Costo medio per metro (C/L) per fascia e profilo

| fascia | riferimento | donna | donna+giovani_16_34 | over75 | disabilita |
|---|---|---|---|---|---|
| giorno | 1.33 | 1.65 | 1.64 | 1.39 | 1.38 |
| sera | 1.39 | 1.84 | 1.85 | 1.49 | 1.47 |
| notte_fonda | 1.45 | 1.96 | 1.97 | 1.56 | 1.53 |

### Affidabilità media per fascia

| fascia | media | min | max |
|---|---|---|---|
| giorno | 0.47 | 0.36 | 0.59 |
| prima_ora_buio | 0.51 | 0.39 | 0.64 |
| sera | 0.54 | 0.41 | 0.69 |
| notte_fonda | 0.54 | 0.41 | 0.68 |
| mattina_buia | 0.56 | 0.42 | 0.69 |

## Affidabilità media e S per quartiere (sera, riferimento)

Residenti (ISTAT 2021) delle sezioni di censimento attraversate da almeno un tratto rosso, di sera: 59,480 su 110,293 (54%), di cui 30,641 donne e 20,029 over 60 (quote per quartiere del Comune). Conta anche tratti rossi molto brevi (passaggi senza uscita): è un indicatore di priorità, non di rischio.

| quartiere | tratti | lunghezza_km | S_medio | pct_lunghezza_rossa | affidabilita_media | residenti_stimati | residenti_esposti | donne_esposte |
|---|---|---|---|---|---|---|---|---|
| San Pietro Intrigogna | 95 | 16.17 | 25.60 | 84.30 | 0.55 | 331 | 298 | 148 |
| Gogna | 207 | 18.55 | 34.70 | 64.10 | 0.57 | 1243 | 869 | 447 |
| Maddalene | 20 | 1.99 | 34.90 | 49.00 | 0.55 | 352 | 351 | 176 |
| Campedello | 480 | 41.95 | 36.00 | 58.80 | 0.56 | 2994 | 2289 | 1144 |
| Bertesina | 215 | 22.00 | 37.00 | 66.10 | 0.56 | 1442 | 1438 | 758 |
| Monte Berico | 252 | 15.12 | 39.30 | 46.30 | 0.55 | 810 | 787 | 395 |
| Ferrovieri | 696 | 49.83 | 39.30 | 45.00 | 0.53 | 5149 | 2863 | 1458 |
| Riviera Berica | 453 | 33.70 | 40.90 | 41.30 | 0.54 | 3465 | 2536 | 1304 |
| Casale | 1004 | 56.51 | 41.20 | 41.00 | 0.55 | 2325 | 2094 | 1035 |
| Capitello | 166 | 10.32 | 42.60 | 33.70 | 0.57 | 1213 | 1015 | 511 |
| Ospedaletto | 288 | 24.04 | 44.00 | 32.50 | 0.55 | 3613 | 1395 | 724 |
| Bertesinella | 332 | 21.95 | 44.40 | 32.20 | 0.51 | 4216 | 2715 | 1400 |
| Polegge | 144 | 11.56 | 44.60 | 32.50 | 0.55 | 1998 | 1223 | 614 |
| Laghetto | 321 | 23.28 | 45.60 | 25.30 | 0.58 | 1739 | 481 | 258 |
| San Bortolo | 1397 | 80.86 | 46.70 | 27.40 | 0.57 | 10869 | 6904 | 3635 |
| San Felice - Cattane | 2799 | 144.58 | 47.90 | 30.00 | 0.55 | 20567 | 10977 | 5602 |
| San Pio X | 1026 | 57.88 | 49.90 | 22.90 | 0.54 | 12208 | 4571 | 2286 |
| Saviabona | 740 | 42.12 | 51.00 | 18.60 | 0.55 | 8624 | 3520 | 1809 |
| San Lazzaro | 669 | 32.00 | 54.00 | 7.80 | 0.53 | 7057 | 4326 | 2138 |
| Stadio | 374 | 13.31 | 56.40 | 8.60 | 0.54 | 2767 | 1519 | 782 |
| Centro Storico | 1753 | 71.77 | 59.20 | 12.50 | 0.55 | 11673 | 5435 | 2994 |
| Via Quadri | 297 | 14.94 | 60.70 | 2.50 | 0.55 | 5638 | 1874 | 1023 |

## Le 20 vie con S più alto — giorno (riferimento, vie ≥ 100 m)

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Contra' Piazza del Castello | Centro Storico | 134.6 | 94.4 | 90.6 | 0.0 | 0.5 |
| Contra' Frasche del Gambero | Centro Storico | 118.0 | 94.3 | 94.3 | 0.0 | 0.5 |
| Piazzale Alcide De Gasperi | Centro Storico | 200.0 | 93.4 | 89.0 | 0.0 | 0.5 |
| Piazza delle Biade | Centro Storico | 120.3 | 92.7 | 91.2 | 0.0 | 0.5 |
| Piazza del Castello | Centro Storico | 218.0 | 92.7 | 81.7 | 0.0 | 0.5 |
| Contra' Motton Pusterla | Centro Storico | 127.0 | 92.5 | 92.5 | 0.0 | 0.5 |
| Via Cesare Battisti | Centro Storico | 123.5 | 92.4 | 92.3 | 0.0 | 0.5 |
| Contra' Vescovado | Centro Storico | 124.5 | 92.3 | 88.1 | 0.0 | 0.5 |
| Contra' Fedele Lampertico | Centro Storico | 105.8 | 92.0 | 89.1 | 0.0 | 0.5 |
| Corso Antonio Fogazzaro | Centro Storico | 628.7 | 91.6 | 42.0 | 0.0 | 0.5 |
| Contra' San Francesco Vecchio | Centro Storico | 192.1 | 91.3 | 90.4 | 0.0 | 0.5 |
| Contra' Pusterla | Centro Storico | 111.7 | 90.7 | 86.1 | 0.0 | 0.5 |
| Contra' Porti | Centro Storico | 235.7 | 90.0 | 82.2 | 0.0 | 0.5 |
| Stradella dei Munari | Centro Storico | 106.3 | 89.6 | 80.7 | 0.0 | 0.5 |
| Contra' Pedemuro San Biagio | Centro Storico | 330.0 | 89.6 | 69.1 | 0.0 | 0.5 |
| Piazza dei Signori | Centro Storico | 192.4 | 87.6 | 54.3 | 0.0 | 0.5 |
| Contra' Riale | Centro Storico | 205.8 | 87.5 | 83.0 | 0.0 | 0.5 |
| Contra' Santi Apostoli | Centro Storico | 197.9 | 87.4 | 78.2 | 0.0 | 0.4 |
| Corso Santi Felice e Fortunato | Centro Storico | 373.8 | 87.3 | 82.4 | 0.0 | 0.4 |
| Leva' degli Angeli | Centro Storico | 100.6 | 86.9 | 85.6 | 0.0 | 0.4 |

## Le 20 vie con S più basso (priorità di intervento) — giorno

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Via Ferdinando Maria Mantovani | Campedello | 899.3 | 24.0 | 19.2 | 100.0 | 0.5 |
| Strada della Cresolella | Laghetto | 357.1 | 24.0 | 22.0 | 100.0 | 0.5 |
| Strada dell'Acquedotto Romano | Capitello | 224.7 | 24.5 | 24.5 | 100.0 | 0.5 |
| Strada Val di Bugano | Riviera Berica | 882.2 | 25.9 | 22.0 | 100.0 | 0.6 |
| Via delle Due Ferrate | Gogna | 452.0 | 26.1 | 25.4 | 100.0 | 0.5 |
| Via Alessandro Avogadro Casanova | Monte Berico | 155.2 | 26.5 | 26.5 | 100.0 | 0.6 |
| Strada dei Rocoli | Monte Berico | 1149.7 | 26.5 | 26.4 | 100.0 | 0.5 |
| Strada di Vallarsa | Capitello | 243.4 | 27.2 | 27.2 | 100.0 | 0.4 |
| Strada Ponte del Bo | Capitello | 121.6 | 28.8 | 28.8 | 100.0 | 0.4 |
| Via Ferdinando Maria Mantovani | Gogna | 944.3 | 29.2 | 21.4 | 100.0 | 0.5 |
| Strada della Colombaretta | Ferrovieri | 742.2 | 29.3 | 28.8 | 100.0 | 0.5 |
| Strada vicinale del Monte Crocetta | San Felice - Cattane | 1342.4 | 29.4 | 20.2 | 94.2 | 0.5 |
| Strada Businello | San Pietro Intrigogna | 2752.4 | 29.5 | 24.5 | 100.0 | 0.5 |
| Strada Maglio di Lobia | San Felice - Cattane | 270.6 | 29.5 | 29.5 | 100.0 | 0.6 |
| Strada dell'Ospedaletto | Bertesina | 2995.7 | 29.6 | 20.1 | 96.3 | 0.5 |
| Via Battaglione Valtellina | San Felice - Cattane | 610.9 | 29.9 | 28.2 | 100.0 | 0.5 |
| Strada Dal Martello | San Felice - Cattane | 378.5 | 30.2 | 16.8 | 100.0 | 0.5 |
| Via Giambattista Remondini | Bertesina | 272.9 | 30.4 | 30.4 | 100.0 | 0.5 |
| Via Battaglione Feltre | San Felice - Cattane | 201.0 | 30.5 | 30.5 | 100.0 | 0.5 |
| Strada dei Rocoli | Campedello | 234.7 | 30.8 | 26.5 | 100.0 | 0.5 |

## Le 20 vie con S più alto — sera (riferimento, vie ≥ 100 m)

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Piazza delle Biade | Centro Storico | 120.3 | 86.1 | 82.7 | 0.0 | 0.5 |
| Contra' Frasche del Gambero | Centro Storico | 118.0 | 81.8 | 81.8 | 0.0 | 0.5 |
| Via Livio Zambeccari | Via Quadri | 145.9 | 81.4 | 81.4 | 0.0 | 0.5 |
| Stradella dei Munari | Centro Storico | 106.3 | 80.4 | 77.0 | 0.0 | 0.6 |
| Contra' Pedemuro San Biagio | Centro Storico | 330.0 | 80.4 | 66.2 | 0.0 | 0.6 |
| Contra' Venti Settembre | Centro Storico | 159.6 | 79.5 | 71.2 | 0.0 | 0.5 |
| Piazzola Gualdi | Centro Storico | 123.4 | 79.3 | 74.3 | 0.0 | 0.5 |
| Corso Antonio Fogazzaro | Centro Storico | 628.7 | 79.1 | 38.2 | 0.9 | 0.6 |
| Contra' Motton Pusterla | Centro Storico | 127.0 | 78.6 | 78.6 | 0.0 | 0.5 |
| Via Cesare Battisti | Centro Storico | 123.5 | 78.4 | 77.9 | 0.0 | 0.6 |
| Contra' Pusterla | Centro Storico | 111.7 | 77.5 | 60.3 | 0.0 | 0.5 |
| Contra' Oratorio dei Servi | Centro Storico | 143.8 | 77.4 | 73.7 | 0.0 | 0.6 |
| Contra' delle Barche | Centro Storico | 300.0 | 77.3 | 59.0 | 0.0 | 0.5 |
| Contra' Jacopo Cabianca | Centro Storico | 170.6 | 77.0 | 62.7 | 0.0 | 0.6 |
| Contra' Sant'Ambrogio | Centro Storico | 106.8 | 76.3 | 76.3 | 0.0 | 0.5 |
| Piazza dei Signori | Centro Storico | 192.4 | 76.1 | 33.6 | 14.1 | 0.6 |
| Contra' Porta Padova | Centro Storico | 331.6 | 75.9 | 68.8 | 0.0 | 0.5 |
| Stradella Soccorso Soccorsetto | Centro Storico | 169.4 | 75.6 | 75.6 | 0.0 | 0.5 |
| Contra' Piazza del Castello | Centro Storico | 134.6 | 75.3 | 65.9 | 0.0 | 0.5 |
| Contra' Giuseppe Apolloni | Centro Storico | 114.0 | 75.2 | 69.4 | 0.0 | 0.5 |

## Le 20 vie con S più basso (priorità di intervento) — sera

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Via Alessandro Avogadro Casanova | Monte Berico | 155.2 | 10.7 | 10.7 | 100.0 | 0.7 |
| Strada della Cresolella | Laghetto | 357.1 | 11.3 | 10.5 | 98.9 | 0.6 |
| Strada dell'Acquedotto Romano | Capitello | 224.7 | 13.8 | 13.8 | 100.0 | 0.6 |
| Strada di Vallarsa | Capitello | 243.4 | 15.0 | 15.0 | 100.0 | 0.5 |
| Via dei Capuleti | San Lazzaro | 153.2 | 15.2 | 15.2 | 100.0 | 0.5 |
| Strada Val di Bugano | Riviera Berica | 882.2 | 15.5 | 11.9 | 98.0 | 0.7 |
| Sentiero Parco Villa Guiccioli | Campedello | 424.0 | 16.1 | 9.2 | 100.0 | 0.7 |
| Strada Maglio di Lobia | San Felice - Cattane | 270.6 | 16.2 | 16.2 | 100.0 | 0.7 |
| Via Ferdinando Maria Mantovani | Campedello | 899.3 | 16.6 | 12.0 | 100.0 | 0.6 |
| Via Giambattista Remondini | Bertesina | 272.9 | 16.6 | 16.6 | 100.0 | 0.6 |
| Strada della Colombaretta | Ferrovieri | 742.2 | 16.8 | 15.0 | 93.5 | 0.6 |
| Strada vicinale del Monte Crocetta | San Felice - Cattane | 1342.4 | 18.5 | 11.6 | 94.2 | 0.6 |
| Strada Businello | San Pietro Intrigogna | 2752.4 | 18.9 | 13.4 | 99.7 | 0.6 |
| Via delle Due Ferrate | Gogna | 452.0 | 19.6 | 15.9 | 100.0 | 0.6 |
| Via Foscarina | Casale | 773.6 | 20.3 | 16.8 | 100.0 | 0.6 |
| Contra' della Caimpenta | Casale | 325.8 | 22.6 | 21.7 | 100.0 | 0.5 |
| Via Cresole | Polegge | 254.1 | 22.7 | 13.0 | 96.5 | 0.6 |
| Via dei Camaldolesi | Saviabona | 625.0 | 23.0 | 17.7 | 84.7 | 0.6 |
| Via della Meccanica | Ferrovieri | 796.9 | 23.0 | 16.8 | 97.3 | 0.5 |
| Viale Cesare Augusto | Casale | 129.9 | 24.2 | 23.6 | 100.0 | 0.5 |

## Le 20 vie con S più alto — notte fonda (riferimento, vie ≥ 100 m)

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Piazzola Gualdi | Centro Storico | 123.4 | 73.8 | 70.4 | 0.0 | 0.5 |
| Piazza dei Signori | Centro Storico | 192.4 | 73.4 | 30.2 | 14.1 | 0.6 |
| Contra' Pedemuro San Biagio | Centro Storico | 330.0 | 70.9 | 60.0 | 0.0 | 0.6 |
| Via Cesare Battisti | Centro Storico | 123.5 | 69.8 | 69.5 | 0.0 | 0.6 |
| Contra' San Faustino | Centro Storico | 202.2 | 69.4 | 67.9 | 0.0 | 0.5 |
| Stradella dei Munari | Centro Storico | 106.3 | 69.3 | 68.1 | 0.0 | 0.6 |
| Contra' Motton Pusterla | Centro Storico | 127.0 | 69.2 | 69.2 | 0.0 | 0.5 |
| Piazza delle Biade | Centro Storico | 120.3 | 67.9 | 59.9 | 0.0 | 0.5 |
| Contra' Giuseppe Apolloni | Centro Storico | 114.0 | 67.8 | 62.4 | 0.0 | 0.5 |
| Leva' degli Angeli | Centro Storico | 100.6 | 67.6 | 66.2 | 0.0 | 0.5 |
| Contra' Mure San Michele | Centro Storico | 153.5 | 67.6 | 67.6 | 0.0 | 0.6 |
| Contra' Santi Apostoli | Centro Storico | 197.9 | 66.7 | 45.5 | 0.0 | 0.5 |
| Contra' Oratorio dei Servi | Centro Storico | 143.8 | 66.2 | 62.8 | 0.0 | 0.6 |
| Contra' Giovanni Busato | Centro Storico | 147.2 | 66.1 | 59.0 | 0.0 | 0.5 |
| Corso Antonio Fogazzaro | Centro Storico | 628.7 | 66.0 | 35.1 | 0.9 | 0.5 |
| Contra' Piazza del Castello | Centro Storico | 134.6 | 66.0 | 54.8 | 0.0 | 0.5 |
| Contra' Venti Settembre | Centro Storico | 159.6 | 65.9 | 57.7 | 0.0 | 0.5 |
| Contra' Frasche del Gambero | Centro Storico | 118.0 | 65.8 | 65.8 | 0.0 | 0.5 |
| Via Firenze | San Felice - Cattane | 104.4 | 65.6 | 59.6 | 0.0 | 0.6 |
| Stradella dei Cappuccini | San Felice - Cattane | 277.0 | 65.4 | 58.5 | 0.0 | 0.5 |

## Le 20 vie con S più basso (priorità di intervento) — notte fonda

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Via Alessandro Avogadro Casanova | Monte Berico | 155.2 | 10.0 | 10.0 | 100.0 | 0.7 |
| Strada della Cresolella | Laghetto | 357.1 | 10.1 | 9.3 | 100.0 | 0.6 |
| Via dei Capuleti | San Lazzaro | 153.2 | 12.0 | 12.0 | 100.0 | 0.5 |
| Strada dell'Acquedotto Romano | Capitello | 224.7 | 13.3 | 13.3 | 100.0 | 0.6 |
| Strada di Vallarsa | Capitello | 243.4 | 14.5 | 14.5 | 100.0 | 0.5 |
| Strada Val di Bugano | Riviera Berica | 882.2 | 14.8 | 11.3 | 100.0 | 0.7 |
| Via Giambattista Remondini | Bertesina | 272.9 | 15.2 | 15.2 | 100.0 | 0.6 |
| Sentiero Parco Villa Guiccioli | Campedello | 424.0 | 15.3 | 8.8 | 100.0 | 0.7 |
| Strada Maglio di Lobia | San Felice - Cattane | 270.6 | 15.4 | 15.4 | 100.0 | 0.7 |
| Strada della Colombaretta | Ferrovieri | 742.2 | 15.5 | 13.7 | 93.5 | 0.6 |
| Via Ferdinando Maria Mantovani | Campedello | 899.3 | 15.8 | 11.5 | 100.0 | 0.6 |
| Strada Businello | San Pietro Intrigogna | 2752.4 | 16.8 | 12.4 | 99.7 | 0.6 |
| Strada vicinale del Monte Crocetta | San Felice - Cattane | 1342.4 | 16.9 | 11.1 | 94.2 | 0.6 |
| Via delle Due Ferrate | Gogna | 452.0 | 18.7 | 15.1 | 100.0 | 0.6 |
| Via Foscarina | Casale | 773.6 | 19.0 | 15.6 | 100.0 | 0.6 |
| Contra' della Caimpenta | Casale | 325.8 | 19.2 | 19.0 | 100.0 | 0.5 |
| Via Cresole | Polegge | 254.1 | 19.2 | 10.3 | 100.0 | 0.6 |
| Viale Cesare Augusto | Casale | 129.9 | 20.7 | 20.5 | 100.0 | 0.5 |
| Via della Meccanica | Ferrovieri | 796.9 | 21.4 | 15.6 | 97.3 | 0.5 |
| Via dei Camaldolesi | Saviabona | 625.0 | 21.7 | 16.7 | 84.7 | 0.6 |

## Parametri esclusi

Episodi segnalati, cura e degrado, composizione della folla: nessuna fonte pubblica. Sono esclusi e i pesi sono rinormalizzati sugli altri (`unmeasured_strategy: renormalize`). Si attiveranno con le segnalazioni dei cittadini (fase 5).
