# Piano per passare ai dati reali

Per la demo il backend usa **dati pubblici reali oppure stime dichiarate come tali**.
L'unica cosa inventata sono tre eventi dimostrativi in `data/demo/`, che entrano nei
calcoli solo con l'opzione `--demo`. Questa pagina dice, fonte per fonte, cosa si usa
oggi e come arrivare al dato reale. Ogni sostituzione si fa mettendo un file in
`data/manual/` o aprendo la rete: il codice non va toccato.

## Perché alcune fonti non sono arrivate

Con la rete dell'ambiente aperta (16/10/2026) sono arrivati ISTAT, le tabelle del Comune su
dati.veneto.it e Nominatim. Restano fuori:

- **Overpass e SIT**: i loro server chiudono la connessione verso questo ambiente cloud.
  Da un computer del team (meglio se in Italia) funzionano: `python -m pipeline.run_all --force`.
- **Open-Meteo**: limite giornaliero superato dall'indirizzo condiviso; dal vostro computer funziona.
- **Eventi del Comune**: il `robots.txt` vieta le API; serve un export o l'accesso dal Comune.
- **GTFS SVT, Punti Viola, punti luce**: non sono pubblici; vanno chiesti.

Ogni fonte si sblocca anche mettendo i file in `data/manual/` (cartelle indicate sotto).

## Fonte per fonte

| Dato | Oggi | Natura | Dato reale da ottenere | Come | Dove metterlo | Priorità |
|---|---|---|---|---|---|---|
| **Punti luce** | `lit` OSM (11% dei tratti), vie adiacenti (8%), lampioni OSM (12%), **modello statistico (68%)** | stima dichiarata (`proxy`, `fonte_luce`) | censimento dei punti luce City Green Light | richiesta al Comune / referente SIT (testo pronto sotto) | `data/manual/punti_luce/` (CSV `lat,lon` o shapefile) | **alta** |
| Confini dei quartieri | 22 zone ufficiali ricostruite da sezioni ISTAT e popolazione del Comune | ricostruzione da dati reali | confini delle zone dal SIT | download dal SIT (da un computer in Italia) o richiesta | `data/manual/sit/` (nome file con "quart") | media |
| Popolazione | ISTAT 2021 per sezione; donne e over 60 dalle quote del Comune per quartiere | dato reale | — (già il dato del brief) | — | — | — |
| Negozi e locali | OSM (1.174) + Overture Places (4.493) | dati reali | orari di apertura (noti solo per il 16% in OSM) | mappatura in OSM (es. app StreetComplete), elenchi del SUAP comunale | OSM o `data/manual/` | media |
| Frequenza dei bus | stima per fascia in `config.yaml` (sera a chiamata ChiamaBus 20:30–23:30) | stima dichiarata (`proxy`) | GTFS di SVT | non è pubblico: chiederlo a SVT o alla Regione | `data/manual/gtfs/` (da integrare, ~2 ore) | media |
| Meteo | Open-Meteo (dal computer del team); qui `sereno` dichiarato; override | nessun dato inventato | — | rete senza limiti | — | bassa |
| Eventi | **3 eventi inventati** in `data/demo/eventi_demo.csv`, solo con `--demo` | simulato, etichettato | agenda "Viva" del Comune | export iCal/CSV o accesso al calendario (il robots.txt vieta le API) | `data/manual/eventi.csv` (stesse colonne) | media |
| Punti Viola | nessuno | **non simulati di proposito** | elenco DonneXStrada | accordo con l'associazione | `data/manual/punti_viola.csv` | media |
| Zonizzazione PI | `landuse` OSM (74% della superficie); attributi del PI scaricati da dati.veneto.it, senza geometria | dato reale | geometrie del PI dal SIT + legenda | download o richiesta | `data/manual/sit/` + `pi_zone_map` in config | bassa |
| OSM | planet su AWS, dati al 12/10/2026 | dato reale | — (Overpass dà gli stessi dati, più aggiornati) | `--force` dal computer del team | — | — |

I Punti Viola non vanno simulati: in una demo pubblica un punto di accoglienza inventato
potrebbe indirizzare qualcuno verso un luogo che non offre aiuto. Lo stesso vale per
episodi e segnalazioni su vie reali: le simulazioni di segnalazioni (fase 5) restano in
un database separato.

## Piano per la luce

La luce è il parametro più pesato di notte (15 su 100). Oggi è **stimata** per due
tratti su tre.

### Come funziona la stima
Un classificatore (gradient boosting, `pipeline/light_model.py`) è addestrato sui 1.494
tratti dove OSM dice se la via è illuminata. Usa solo dati presenti ovunque: classe
della strada, edifici e popolazione vicini, uso del suolo, parchi, fondo sterrato,
lampioni mappati, distanza dal centro. Validazione per quartiere (il modello è provato
su quartieri che non ha visto): **AUC 0,87, accuratezza 93%** contro il 91% di chi
risponde sempre "illuminato"; riconosce circa metà dei tratti non illuminati. Il valore
usato è la probabilità di essere illuminato. Ogni tratto porta `fonte_luce` (nel
GeoJSON e nel tooltip della mappa), così la stima non si confonde mai con una misura.

**Cosa dire in demo:** «La luce è misurata dove OpenStreetMap la conosce e stimata
altrove, con un modello addestrato su quei dati, accuratezza del 93% su quartieri
che il modello non aveva visto. Quando il Comune ci darà i punti luce, li inseriamo senza
cambiare codice e l'affidabilità sale».

### Passi per avere il dato reale

| Quando | Azione | Chi | Effetto |
|---|---|---|---|
| prima della demo | nessuna: la stima è già attiva | — | mappa completa, flag `proxy` |
| settimana 1 | richiesta formale dei punti luce (testo sotto) | team → Comune / SIT | se arriva: Luce `measured` ovunque |
| settimana 1 | chiedere anche le tavole del PICIL 2012 (classificazione illuminotecnica delle strade) | team → SIT | proxy migliore della stima, per via |
| settimana 1–2 | token gratuito Mapillary → scaricare i lampioni rilevati dalle foto | team (token) + sviluppo (~2 ore) | più lampioni dove OSM non li ha |
| settimana 2–4 | compositi notturni SDGSAT-1 del JRC (10–40 m) → valore medio lungo il tratto | sviluppo (~4 ore), verificare licenza | proxy misurato dal satellite, uniforme sulla città |
| continuo | segnalazioni `luce_scarsa` e `lampione_guasto` dei cittadini (fase 5) | utenti | correzioni puntuali, aggiornate |
| continuo | passeggiate di mappatura: tag `lit` e lampioni in OSM | volontari | migliora sia il dato sia il modello |
| quando arriva il dato reale | confrontare la stima con i punti luce veri e riportare l'errore nel report | sviluppo | verifica onesta della stima |

### Testo per la richiesta dei punti luce

> Oggetto: richiesta dati sull'illuminazione pubblica per il progetto «Quartieri Vivi»
> (TechWarriors Vicenza 2026, sfida Urbanistica)
>
> Buongiorno, per il progetto «Quartieri Vivi» stiamo costruendo una mappa della
> sicurezza percepita nelle strade di Vicenza a partire da dati pubblici, per individuare
> priorità di intervento. L'illuminazione è il fattore che pesa di più di notte.
> Chiediamo, se possibile, un estratto del censimento dei punti luce gestiti da City
> Green Light: coordinate (o shapefile), e se disponibili tipo di sorgente (LED o altro),
> potenza, altezza, regolazione notturna. Va bene anche un CSV parziale. In alternativa,
> le tavole del PICIL con la classificazione illuminotecnica delle strade. I dati saranno
> usati solo in forma aggregata per tratto di strada e citati come fonte. Grazie.

## Altre stime e sostituti oggi in uso

- **Residenti esposti**: residenti ISTAT 2021 delle sezioni attraversate da tratti rossi
  (come nel brief); donne e over 60 stimati con le quote per quartiere del Comune.
- **Attività senza orario**: orari predefiniti per categoria (`config.yaml -> pois.default_hours`).
- **Persone e visuale**: sempre `proxy` per definizione (nessuna misura diretta).
- **Episodi, cura, composizione della folla**: esclusi finché non arrivano le segnalazioni (fase 5).
