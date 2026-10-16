# Validazione del punteggio — Vicenza

*Il punteggio stima la sicurezza percepita a partire dai dati disponibili. Non misura la sicurezza reale di un luogo.*

Dati OSM al 2026-10-12T00:00:02Z (fonte: https://osm-pds.s3.amazonaws.com/planet-latest.osm.pbf). Data di riferimento: 2026-11-18 (feriale), ore di riferimento per fascia: giorno 11:00, sera 20:00, notte_fonda 23:30.

Nei testi si parla di **criticità percepite** e **priorità di intervento**: il punteggio non individua zone pericolose.

## Controlli di coerenza

| controllo | esito | dettaglio |
|---|---|---|
| Di sera le vie pedonali del centro storico hanno S medio più alto delle zone industriali | PASS | vie pedonali del centro storico (entro 600 m da Piazza dei Signori (coordinate fisse)): S = 60.2 su 474 tratti; tratti in aree `landuse=industrial`: S = 28.8 su 178 tratti |
| I sottopassi (e i passaggi coperti o senza uscita) risultano penalizzati | PASS | 1,010 tratti con penalità −30% (75 sottopassi, 91 coperti o passaggi sotto edifici, 864 passaggi pedonali senza uscita): S medio 28.6 contro 47.1 degli altri tratti |
| Di giorno la luce pesa molto meno | PASS | peso luce giorno 2.0% vs sera 15.0%; passare da luce 0 a 1 vale in media 2.9 punti di giorno e 18.9 di sera |
| Il profilo «donna» non alza mai S rispetto al riferimento sullo stesso tratto con luce scarsa | FAIL | 2,509 tratti con luce < 0,5 di sera: per il profilo donna S scende in 1,995 e sale in 514 (20%, al massimo di +2.51 punti); variazione media -0.67 punti. Motivo: è una proprietà del modello, non un errore di calcolo. Il profilo donna aumenta anche i pesi di visuale e uso del suolo; dopo la rinormalizzazione perdono peso i parametri non moltiplicati (vie di fuga, fronti attivi, punti di aiuto). Dove questi sono bassi e visuale e uso del suolo alti, S sale di poco anche al buio. Cambiare solo i moltiplicatori non basta: con luce ×2 i tratti restano 65, con luce ×3 56. Per garantire il controllo serve una penalità di buio specifica del profilo: è una decisione del team. Il costo per il navigatore invece cresce sempre (controllo successivo). |
| (aggiuntivo) Sui tratti con luce scarsa il costo per metro del profilo donna non è mai inferiore al riferimento | PASS | costo medio per metro 2.28 (donna, λ = 3) contro 1.63 (riferimento, λ = 1,5); tratti con costo inferiore: 0 |
| Nessun tratto ha S fuori da 0–100 | PASS | 0 valori fuori intervallo su 205,920 |
| Nessun NaN nei punteggi | PASS | 0 valori mancanti in S, affidabilità e costo |

## Copertura dei dati

- Tratti pedonali: 13,728 (804.4 km); tratti con `lit`: 12.1% della lunghezza; lampioni OSM: 2,835; attività con `opening_hours`: 15.7% di 999; strade veicolari con `sidewalk`: 11.4%.
- Dettaglio completo in `reports/osm_coverage.md`; stato delle fonti in `DATA_SOURCES.md`.

### Origine dei valori per parametro (fascia sera, % dei tratti)

| parametro | measured % | proxy % | excluded % | valore medio |
|---|---|---|---|---|
| Luce | 10.9 | 36.1 | 53.0 | 0.6 |
| Presenza di persone | 0.0 | 100.0 | 0.0 | 0.2 |
| Fronti attivi | 82.5 | 17.5 | 0.0 | 0.1 |
| Visuale libera | 0.0 | 100.0 | 0.0 | 0.7 |
| Vie di fuga | 100.0 | 0.0 | 0.0 | 0.8 |
| Uso del suolo | 80.5 | 0.0 | 19.5 | 0.7 |
| Episodi segnalati | 0.0 | 0.0 | 100.0 |  |
| Cura e degrado | 0.0 | 0.0 | 100.0 |  |
| Qualità del percorso | 33.0 | 67.0 | 0.0 | 0.7 |
| Composizione della folla | 0.0 | 0.0 | 100.0 |  |
| Punti di aiuto | 36.8 | 63.2 | 0.0 | 0.4 |
| Trasporto e attesa | 6.1 | 93.9 | 0.0 | 0.4 |

## Distribuzione di S per fascia e profilo

| fascia | profilo | media | p10 | mediana | p90 | min | max | % rossi | % verdi |
|---|---|---|---|---|---|---|---|---|---|
| giorno | riferimento | 52.8 | 34.9 | 52.9 | 70.1 | 11.3 | 95.7 | 18.8 | 17.0 |
| giorno | donna | 53.0 | 35.2 | 53.1 | 70.3 | 11.4 | 94.9 | 18.2 | 17.4 |
| giorno | donna+giovani_16_34 | 53.4 | 35.4 | 53.8 | 70.7 | 11.1 | 95.0 | 17.6 | 18.5 |
| giorno | over75 | 55.3 | 38.5 | 54.6 | 73.3 | 15.0 | 96.7 | 12.9 | 23.9 |
| giorno | disabilita | 56.2 | 39.4 | 55.6 | 74.1 | 15.2 | 96.8 | 10.9 | 26.1 |
| sera | riferimento | 45.7 | 27.2 | 46.1 | 62.8 | 6.8 | 91.9 | 34.0 | 7.1 |
| sera | donna | 46.3 | 27.6 | 46.6 | 64.2 | 6.8 | 91.6 | 33.2 | 8.9 |
| sera | donna+giovani_16_34 | 46.3 | 27.6 | 46.5 | 64.0 | 6.7 | 91.1 | 33.1 | 8.6 |
| sera | over75 | 47.5 | 29.2 | 47.7 | 64.7 | 7.7 | 92.9 | 30.0 | 9.5 |
| sera | disabilita | 49.0 | 29.7 | 49.6 | 66.0 | 7.5 | 93.1 | 25.7 | 11.6 |
| notte_fonda | riferimento | 41.2 | 24.2 | 41.5 | 56.9 | 6.5 | 86.3 | 45.5 | 1.9 |
| notte_fonda | donna | 41.9 | 24.8 | 42.2 | 58.5 | 6.5 | 85.8 | 44.6 | 2.4 |
| notte_fonda | donna+giovani_16_34 | 41.3 | 24.5 | 41.6 | 57.7 | 6.4 | 84.8 | 45.9 | 2.0 |
| notte_fonda | over75 | 43.4 | 26.6 | 43.7 | 59.2 | 7.1 | 87.8 | 39.8 | 3.5 |
| notte_fonda | disabilita | 44.9 | 27.2 | 45.5 | 60.7 | 7.0 | 88.1 | 35.5 | 4.6 |

S cambia poco da un profilo all'altro, come previsto dal modello (PDF, esempio di calcolo): i profili spostano peso tra parametri, quindi S cambia solo dove un parametro molto pesato per quel profilo è molto diverso dagli altri. Over 75 e disabilità hanno S medio più alto perché pesano molto la qualità del percorso, che in media è buona. L'effetto principale del profilo è sul **costo per il navigatore** (λ): stesso tratto, costo più alto per chi è più sensibile al rischio.

### Costo medio per metro (C/L) per fascia e profilo

| fascia | riferimento | donna | donna+giovani_16_34 | over75 | disabilita |
|---|---|---|---|---|---|
| giorno | 1.36 | 1.72 | 1.71 | 1.43 | 1.41 |
| sera | 1.47 | 1.92 | 1.92 | 1.57 | 1.55 |
| notte_fonda | 1.54 | 2.06 | 2.08 | 1.65 | 1.62 |

### Affidabilità media per fascia

| fascia | media | min | max |
|---|---|---|---|
| giorno | 0.48 | 0.35 | 0.59 |
| prima_ora_buio | 0.50 | 0.34 | 0.64 |
| sera | 0.52 | 0.34 | 0.69 |
| notte_fonda | 0.51 | 0.34 | 0.68 |
| mattina_buia | 0.52 | 0.35 | 0.69 |

## Affidabilità media e S per quartiere (sera, riferimento)

| quartiere | tratti | lunghezza_km | S_medio | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|
| Maddalene Vecchie | 44 | 11.75 | 24.00 | 98.50 | 0.50 |
| Gogna | 154 | 19.25 | 25.80 | 96.70 | 0.52 |
| Monte Berico | 246 | 22.63 | 27.40 | 90.60 | 0.53 |
| Bertesina | 168 | 16.65 | 31.90 | 81.60 | 0.50 |
| Saviabona | 89 | 10.37 | 32.70 | 77.90 | 0.47 |
| Pomari | 589 | 38.91 | 34.00 | 71.70 | 0.52 |
| Settecà | 1027 | 65.30 | 34.10 | 65.20 | 0.52 |
| Maddalene | 44 | 5.26 | 35.00 | 67.30 | 0.48 |
| Casale | 756 | 58.86 | 35.20 | 65.00 | 0.49 |
| Bertesinella | 256 | 17.23 | 36.40 | 61.20 | 0.46 |
| Polegge | 177 | 16.83 | 36.90 | 56.80 | 0.53 |
| Ospedaletto | 138 | 12.02 | 36.90 | 64.00 | 0.52 |
| Capitello | 176 | 18.27 | 37.20 | 53.80 | 0.55 |
| Lobia | 271 | 20.99 | 37.50 | 41.10 | 0.59 |
| Moracchino | 111 | 6.91 | 37.60 | 56.10 | 0.54 |
| Ferrovieri | 477 | 29.56 | 38.10 | 54.30 | 0.48 |
| Villaggio del Sole | 470 | 26.20 | 38.50 | 52.20 | 0.53 |
| La Stanga | 398 | 26.30 | 40.20 | 54.40 | 0.51 |
| Anconetta | 154 | 13.20 | 40.60 | 49.10 | 0.50 |
| Cattane | 369 | 24.06 | 40.80 | 41.00 | 0.53 |
| Borgo Berga | 410 | 18.36 | 40.90 | 51.00 | 0.51 |
| Laghetto | 439 | 27.28 | 44.40 | 29.40 | 0.56 |
| San Pio X | 573 | 32.55 | 45.90 | 28.50 | 0.51 |
| Sant'Andrea | 196 | 10.22 | 47.50 | 20.30 | 0.55 |
| San Felice | 707 | 27.94 | 47.90 | 31.10 | 0.53 |
| San Francesco | 489 | 25.02 | 48.10 | 21.70 | 0.53 |
| Santa Caterina | 249 | 11.75 | 48.60 | 27.50 | 0.49 |
| San Bortolo | 641 | 28.13 | 48.90 | 23.10 | 0.55 |
| San Paolo | 668 | 32.17 | 49.40 | 20.90 | 0.51 |
| San Giuseppe | 557 | 21.09 | 50.20 | 18.40 | 0.51 |
| Santa Lucia | 372 | 13.62 | 51.90 | 20.00 | 0.54 |
| San Lazzaro | 222 | 10.66 | 52.00 | 11.80 | 0.51 |
| Stadio | 284 | 11.70 | 52.20 | 9.00 | 0.48 |
| San Biagio | 369 | 17.32 | 52.90 | 14.30 | 0.53 |
| Santa Bertilla | 508 | 20.86 | 53.90 | 6.20 | 0.53 |
| Araceli | 203 | 10.06 | 54.30 | 5.50 | 0.50 |
| Centro storico | 439 | 16.12 | 58.30 | 14.70 | 0.54 |
| Barche | 288 | 9.02 | 59.10 | 9.80 | 0.54 |

## Le 20 vie con S più alto — giorno (riferimento, vie ≥ 100 m)

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Piazza dei Signori | Centro storico | 164.3 | 95.3 | 94.9 | 0.0 | 0.5 |
| Corso Antonio Fogazzaro | Centro storico | 196.6 | 95.0 | 94.3 | 0.0 | 0.5 |
| Contra' Piazza del Castello | Centro storico | 134.6 | 93.5 | 92.7 | 0.0 | 0.5 |
| Contra' Frasche del Gambero | Centro storico | 118.0 | 92.6 | 92.6 | 0.0 | 0.5 |
| Contra' Pusterla | San Biagio | 111.7 | 92.0 | 89.6 | 0.0 | 0.5 |
| Via Cesare Battisti | Centro storico | 123.5 | 91.7 | 89.2 | 0.0 | 0.5 |
| Piazza delle Biade | Barche | 120.3 | 91.3 | 84.7 | 0.0 | 0.5 |
| Corso Andrea Palladio | Centro storico | 626.5 | 91.3 | 60.1 | 0.0 | 0.5 |
| Piazzale Alcide De Gasperi | Centro storico | 200.0 | 91.0 | 88.3 | 0.0 | 0.5 |
| Piazza del Castello | Centro storico | 218.0 | 90.4 | 87.4 | 0.0 | 0.5 |
| Contra' Motton Pusterla | San Biagio | 127.0 | 86.5 | 86.5 | 0.0 | 0.5 |
| Contra' Vescovado | Centro storico | 124.5 | 85.9 | 74.7 | 0.0 | 0.5 |
| Contra' Porti | San Biagio | 152.9 | 85.6 | 85.6 | 0.0 | 0.5 |
| Contra' Do Rode | Centro storico | 125.7 | 85.2 | 63.0 | 0.0 | 0.5 |
| Contra' Santi Apostoli | Barche | 143.3 | 84.9 | 84.9 | 0.0 | 0.4 |
| Stradella dei Filippini | Centro storico | 101.4 | 84.8 | 84.8 | 0.0 | 0.5 |
| Corso Santi Felice e Fortunato | Centro storico | 168.0 | 84.1 | 79.7 | 0.0 | 0.4 |
| Contra' Venti Settembre | Santa Lucia | 159.6 | 83.8 | 71.3 | 0.0 | 0.4 |
| Contra' San Marco | San Biagio | 252.9 | 83.5 | 75.0 | 0.0 | 0.5 |
| Contra' San Francesco Vecchio | Centro storico | 192.1 | 83.4 | 81.0 | 0.0 | 0.5 |

## Le 20 vie con S più basso (priorità di intervento) — giorno

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Strada della Cresolella | Polegge | 357.1 | 24.0 | 22.3 | 100.0 | 0.5 |
| Strada dei Rocoli | Gogna | 1141.2 | 26.0 | 25.3 | 100.0 | 0.5 |
| Strada dell'Acquedotto Romano | Lobia | 224.7 | 26.1 | 26.1 | 100.0 | 0.5 |
| Via delle Due Ferrate | Gogna | 479.9 | 26.3 | 23.4 | 100.0 | 0.5 |
| Strada Val di Bugano | Settecà | 882.2 | 26.3 | 22.3 | 98.0 | 0.6 |
| Via Ferdinando Maria Mantovani | Gogna | 1202.8 | 27.0 | 20.0 | 100.0 | 0.5 |
| Via Sebastiano Venier | Casale | 256.0 | 27.3 | 27.3 | 100.0 | 0.5 |
| Strada della Commenda | Monte Berico | 925.9 | 27.6 | 20.4 | 100.0 | 0.5 |
| Strada della Pergoletta | Monte Berico | 812.6 | 28.3 | 20.9 | 100.0 | 0.5 |
| Strada vicinale del Monte Crocetta | Villaggio del Sole | 1342.4 | 28.3 | 21.6 | 94.2 | 0.5 |
| Via Alessandro Avogadro Casanova | Monte Berico | 155.2 | 28.3 | 28.3 | 100.0 | 0.6 |
| Strada della Porciglia | Monte Berico | 787.9 | 28.5 | 24.6 | 100.0 | 0.5 |
| Via dell'Elettronica | Pomari | 244.1 | 28.7 | 28.2 | 95.7 | 0.5 |
| Via Battaglione Valtellina | Pomari | 184.4 | 29.0 | 29.0 | 100.0 | 0.4 |
| Strada Maglio di Lobia | Lobia | 310.1 | 29.4 | 25.6 | 100.0 | 0.6 |
| Strada della Colombaretta | Pomari | 742.2 | 29.4 | 29.0 | 100.0 | 0.5 |
| Via Ponte del Quarelo | Gogna | 657.6 | 29.5 | 25.0 | 100.0 | 0.5 |
| Strada Biron di Sotto | Cattane | 2094.9 | 29.8 | 22.3 | 100.0 | 0.5 |
| Via Battaglione Feltre | Cattane | 201.0 | 29.8 | 29.8 | 100.0 | 0.5 |
| Strada Postumia | Anconetta | 861.2 | 29.8 | 23.9 | 100.0 | 0.5 |

## Le 20 vie con S più alto — sera (riferimento, vie ≥ 100 m)

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Piazza delle Biade | Barche | 120.3 | 86.3 | 78.8 | 0.0 | 0.5 |
| Piazza dei Signori | Centro storico | 164.3 | 83.5 | 76.0 | 0.0 | 0.6 |
| Corso Antonio Fogazzaro | Centro storico | 196.6 | 81.7 | 74.2 | 0.0 | 0.5 |
| Contra' Oratorio dei Servi | Barche | 143.8 | 79.0 | 74.8 | 0.0 | 0.6 |
| Contra' Pusterla | San Biagio | 111.7 | 78.2 | 60.4 | 0.0 | 0.5 |
| Stradella dei Munari | San Biagio | 106.3 | 77.1 | 68.5 | 0.0 | 0.6 |
| Piazzola Gualdi | Santa Caterina | 123.4 | 76.3 | 71.4 | 0.0 | 0.4 |
| Contra' Jacopo Cabianca | Barche | 170.6 | 75.9 | 65.4 | 0.0 | 0.6 |
| Via Firenze | San Felice | 104.4 | 74.7 | 64.4 | 0.0 | 0.6 |
| Piazzale Alcide De Gasperi | Centro storico | 200.0 | 74.2 | 67.9 | 0.0 | 0.5 |
| Corso Andrea Palladio | Centro storico | 626.5 | 73.8 | 57.2 | 0.0 | 0.6 |
| Contra' Mure San Michele | Barche | 153.5 | 73.0 | 73.0 | 0.0 | 0.6 |
| Contra' Giuseppe Apolloni | San Biagio | 114.0 | 72.8 | 62.9 | 0.0 | 0.5 |
| Contra' Santa Corona | San Biagio | 125.2 | 72.6 | 67.8 | 0.0 | 0.6 |
| Contra' San Faustino | Barche | 202.2 | 72.3 | 68.2 | 0.0 | 0.5 |
| Corso Antonio Fogazzaro | San Biagio | 432.2 | 70.8 | 38.8 | 3.0 | 0.6 |
| Contra' Riale | Centro storico | 205.8 | 70.5 | 67.0 | 0.0 | 0.6 |
| Contra' Motton Pusterla | San Biagio | 127.0 | 70.4 | 70.4 | 0.0 | 0.5 |
| Via Antonio Federico Ozanam | Santa Bertilla | 134.5 | 70.1 | 70.1 | 0.0 | 0.6 |
| Via Quattro Novembre | Santa Lucia | 435.5 | 70.0 | 44.8 | 0.0 | 0.6 |

## Le 20 vie con S più basso (priorità di intervento) — sera

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Strada della Cresolella | Polegge | 357.1 | 15.3 | 14.6 | 98.9 | 0.7 |
| Via Alessandro Avogadro Casanova | Monte Berico | 155.2 | 15.4 | 15.4 | 100.0 | 0.7 |
| Via dei Capuleti | Pomari | 153.2 | 19.5 | 19.5 | 100.0 | 0.4 |
| Via Sebastiano Venier | Casale | 256.0 | 19.9 | 19.9 | 100.0 | 0.5 |
| Strada Postumia | Anconetta | 861.2 | 20.3 | 16.6 | 100.0 | 0.6 |
| Strada della Colombaretta | Pomari | 742.2 | 20.8 | 20.0 | 100.0 | 0.6 |
| Strada dei Rocoli | Gogna | 1141.2 | 20.8 | 20.4 | 100.0 | 0.5 |
| Strada Val di Bugano | Settecà | 882.2 | 20.9 | 16.0 | 98.0 | 0.7 |
| Via dell'Elettronica | Pomari | 244.1 | 20.9 | 20.2 | 100.0 | 0.5 |
| Strada Maglio di Lobia | Lobia | 310.1 | 21.3 | 17.1 | 100.0 | 0.7 |
| Sentiero Parco Villa Guiccioli | Monte Berico | 424.0 | 21.5 | 12.2 | 100.0 | 0.7 |
| Strada dell'Acquedotto Romano | Lobia | 224.7 | 21.6 | 21.6 | 100.0 | 0.5 |
| Via Battaglione Valtellina | Pomari | 184.4 | 22.3 | 22.3 | 100.0 | 0.4 |
| Via delle Due Ferrate | Gogna | 479.9 | 23.1 | 19.2 | 100.0 | 0.5 |
| Via Gaetana Sterni | Ospedaletto | 507.4 | 23.3 | 23.3 | 100.0 | 0.5 |
| Strada vicinale del Monte Crocetta | Villaggio del Sole | 1342.4 | 23.4 | 19.0 | 100.0 | 0.5 |
| Strada di Casale | Borgo Berga | 106.2 | 23.5 | 23.5 | 100.0 | 0.5 |
| Strada dei Sartorello | Monte Berico | 417.3 | 23.5 | 23.5 | 100.0 | 0.4 |
| Via Battaglione Feltre | Cattane | 201.0 | 23.5 | 23.5 | 100.0 | 0.5 |
| Strada della Commenda | Monte Berico | 925.9 | 23.5 | 18.6 | 100.0 | 0.5 |

## Le 20 vie con S più alto — notte fonda (riferimento, vie ≥ 100 m)

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Piazza dei Signori | Centro storico | 164.3 | 75.2 | 67.6 | 0.0 | 0.6 |
| Corso Antonio Fogazzaro | Centro storico | 196.6 | 70.5 | 68.2 | 0.0 | 0.5 |
| Piazzola Gualdi | Santa Caterina | 123.4 | 67.8 | 64.9 | 0.0 | 0.5 |
| Contra' Santa Corona | San Biagio | 125.2 | 67.6 | 62.6 | 0.0 | 0.6 |
| Piazzale Alcide De Gasperi | Centro storico | 200.0 | 67.6 | 62.8 | 0.0 | 0.5 |
| Via Firenze | San Felice | 104.4 | 67.4 | 61.1 | 0.0 | 0.6 |
| Contra' Oratorio dei Servi | Barche | 143.8 | 66.5 | 63.0 | 0.0 | 0.6 |
| Contra' Mure San Michele | Barche | 153.5 | 66.3 | 66.3 | 0.0 | 0.6 |
| Contra' Giuseppe Apolloni | San Biagio | 114.0 | 66.2 | 56.8 | 0.0 | 0.5 |
| Contra' Jacopo Cabianca | Barche | 170.6 | 65.8 | 60.6 | 0.0 | 0.6 |
| Contra' San Faustino | Barche | 202.2 | 65.7 | 63.4 | 0.0 | 0.5 |
| Via Antonio Federico Ozanam | Santa Bertilla | 134.5 | 65.5 | 65.5 | 0.0 | 0.6 |
| Corso Andrea Palladio | Centro storico | 626.5 | 65.2 | 47.4 | 0.0 | 0.6 |
| Stradella dei Munari | San Biagio | 106.3 | 65.2 | 63.9 | 0.0 | 0.6 |
| Contra' delle Fontanelle | Santa Lucia | 146.2 | 64.8 | 61.1 | 0.0 | 0.6 |
| Contra' Pasini | Centro storico | 120.3 | 64.5 | 63.4 | 0.0 | 0.6 |
| Contra' Santi Apostoli | Barche | 143.3 | 64.5 | 64.5 | 0.0 | 0.4 |
| Contra' Riale | Centro storico | 205.8 | 64.3 | 63.3 | 0.0 | 0.6 |
| Via Quattro Novembre | Santa Lucia | 435.5 | 63.9 | 39.9 | 13.4 | 0.6 |
| Contra' Pusterla | San Biagio | 111.7 | 63.6 | 46.0 | 0.0 | 0.5 |

## Le 20 vie con S più basso (priorità di intervento) — notte fonda

| via | quartiere | lunghezza_m | S_medio | S_min | pct_lunghezza_rossa | affidabilita_media |
|---|---|---|---|---|---|---|
| Strada della Cresolella | Polegge | 357.1 | 13.3 | 12.7 | 98.9 | 0.6 |
| Via dei Capuleti | Pomari | 153.2 | 14.2 | 14.2 | 100.0 | 0.4 |
| Via Alessandro Avogadro Casanova | Monte Berico | 155.2 | 14.6 | 14.6 | 100.0 | 0.7 |
| Strada Postumia | Anconetta | 861.2 | 17.5 | 14.8 | 100.0 | 0.6 |
| Via Sebastiano Venier | Casale | 256.0 | 18.0 | 18.0 | 100.0 | 0.5 |
| Via dell'Elettronica | Pomari | 244.1 | 18.1 | 17.5 | 100.0 | 0.5 |
| Via Cresole | Polegge | 254.1 | 18.8 | 16.6 | 100.0 | 0.5 |
| Strada della Colombaretta | Pomari | 742.2 | 19.0 | 18.2 | 100.0 | 0.6 |
| Strada Val di Bugano | Settecà | 882.2 | 19.8 | 15.3 | 98.0 | 0.7 |
| Via Battaglione Valtellina | Pomari | 184.4 | 19.8 | 19.8 | 100.0 | 0.4 |
| Viale Dieci Martiri | Borgo Berga | 279.6 | 20.0 | 20.0 | 100.0 | 0.4 |
| Strada dei Rocoli | Gogna | 1141.2 | 20.1 | 19.4 | 100.0 | 0.5 |
| Sentiero Parco Villa Guiccioli | Monte Berico | 424.0 | 20.4 | 11.6 | 100.0 | 0.7 |
| Strada Maglio di Lobia | Lobia | 310.1 | 20.4 | 16.4 | 100.0 | 0.7 |
| Strada di Casale | Borgo Berga | 106.2 | 20.6 | 20.6 | 100.0 | 0.5 |
| Strada dell'Acquedotto Romano | Lobia | 224.7 | 20.7 | 20.7 | 100.0 | 0.5 |
| Strada di Bertesina | San Pio X | 287.9 | 20.8 | 15.4 | 100.0 | 0.5 |
| Strada vicinale del Monte Crocetta | Villaggio del Sole | 1342.4 | 20.8 | 18.0 | 100.0 | 0.5 |
| Strada Businello | Settecà | 2752.4 | 21.4 | 16.5 | 100.0 | 0.6 |
| Tunnel Viale Dante - Valletta del Silenzio | Borgo Berga | 271.9 | 21.6 | 21.6 | 100.0 | 0.5 |

## Parametri esclusi

Episodi segnalati, cura e degrado, composizione della folla: nessuna fonte pubblica. Sono esclusi e i pesi sono rinormalizzati sugli altri (`unmeasured_strategy: renormalize`). Si attiveranno con le segnalazioni dei cittadini (fase 5).
