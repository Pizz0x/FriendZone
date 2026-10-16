# Lumi, l'app per chi cammina

Il progetto ha due interfacce, generate dagli stessi dati con `python -m pipeline.frontend`:

| | Per chi | Cosa fa | File |
|---|---|---|---|
| **Mappa per gli enti** | Comune, pari opportunità, mobilità | tutte le strade colorate per ora, giorno, meteo e profilo; parametri di ogni tratto; quartieri con S più basso | `frontend/enti.html` |
| **Lumi** | cittadine e cittadini | domande iniziali, mappa 3D, percorso consigliato e navigatore, SOS, segnalazioni, supporto, diario | `frontend/lumi.html` |

`frontend/index.html` porta a tutte e due. Le pagine non hanno bisogno di un server: i dati
(13.728 tratti, parametri per le 24 ore di un feriale e di un sabato, edifici, vie e luoghi
per la ricerca) sono dentro il file. Serve internet solo per la libreria della mappa
(MapLibre) e i caratteri. Per usare il GPS del telefono la pagina va aperta da https o da
localhost:

```bash
python -m http.server -d frontend 8000   # poi http://localhost:8000/lumi.html
```

## Da dove parte

Lumi riprende la demo del team (nome, mascotte, colori, schermate, barra in basso,
diario, condivisione della posizione) e la collega al modello del backend.

| Nella demo | In Lumi |
|---|---|
| punteggio proprio: griglia 80×80 con lampioni, `lit` e locali scaricati da Overpass al momento | i punteggi del modello (12 parametri, fasce dal tramonto reale, profilo, penalità di buio) per ogni tratto della rete pedonale |
| mappa OpenFreeMap con edifici colorati dal punteggio | mappa 3D disegnata con i dati del progetto: strade colorate, edifici grigi in rilievo; di notte la mappa diventa scura e le strade "si accendono" |
| percorsi del servizio OSRM, scelto quello con meno metri rossi | percorso a costo minimo sulla rete del progetto, `C = L·(1 + λ·((100−S)/100)²)`, con λ del profilo; si vede anche il più breve, con i metri di differenza |
| indicazioni dei servizi esterni | indicazioni svolta per svolta calcolate dai nomi delle vie, a voce (facoltativa), ricalcolo se ci si allontana di oltre 40 m |
| ricerca con Nominatim e Photon | ricerca senza rete tra 3.249 vie e luoghi di Vicenza: la destinazione non viene mandata a nessuno |

Il calcolo nel browser è lo stesso del Python: `tests/test_frontend_js.py` confronta fasce
orarie, alba e tramonto e percorsi su dati reali; i punteggi differiscono al massimo di
0,19 punti (classe uguale nel 99,9% dei tratti).

## Cosa ho cambiato e perché

### Domande iniziali
Obiettivo: che chiunque le possa fare senza disagio, e che ogni risposta serva a qualcosa.

- **Ogni domanda si salta** (e c'è «Salta le domande» già nella prima schermata). Sotto ogni
  domanda c'è il motivo per cui la facciamo.
- **Tolte** data di nascita, professione e motivo del download: non servono ai percorsi e
  sono dati in più da proteggere. Al posto della data di nascita, **fasce d'età**
  (16–34, 35–64, 65–74, 75+, preferisco non dirlo).
- **Genere**: donna, uomo, persona non binaria, preferisco non dirlo. Decide i pesi
  (profilo «donna» del modello) e la forma con cui l'app scrive (femminile, maschile o
  neutra, modificabile nelle impostazioni). Il nome è facoltativo e può essere un soprannome.
- **Situazioni facoltative, a scelta multipla**: disabilità o difficoltà a camminare,
  comunità LGBTQ+, una molestia recente, «conosco bene Vicenza». Sono i profili del PDF.
  Sono dati delicati: restano sul telefono e il testo lo dice.
- **Quanto allungare la strada** (poco, un po', parecchio): moltiplica λ del profilo
  (0,5 / 1 / 2, in `config.yaml → routing`). È il primo passo verso i profili «più
  flessibili» di cui avevamo parlato.
- Alla fine Lumi **spiega cosa ha adattato** («di sera do più peso a luce e persone…»).
- In ogni percorso si può scegliere **l'ora di partenza, la pioggia e «in compagnia»**
  (profilo del PDF: il buio pesa la metà).

### SOS
Nella demo il pulsante SOS chiedeva la password prima di mostrare il 112, mentre il testo
diceva il contrario. In Lumi **l'SOS non chiede mai il codice**: mostra subito 112 e 1522
(il numero è anche scritto, non solo un link) e propone di mandare la posizione a una
persona di fiducia. Il codice protegge solo le azioni che una persona malintenzionata con
il telefono in mano potrebbe voler fare: fermare la condivisione, togliere contatti,
disattivare la condivisione dei dati, cancellare tutto.

### Linguaggio
Il brief chiede di parlare di criticità percepite e priorità di intervento, mai di zone
pericolose. Tolti «sicuro / a rischio / zona a rischio / strada pericolosa / gente losca».
I colori sono spiegati per quello che misurano (verde: illuminata e frequentata; giallo: più
tranquilla; rosso: poca luce o poche persone) e l'avvertenza «stima, non misura la sicurezza
reale» compare nel tutorial, nella legenda e nelle impostazioni. «Gente losca» spingeva a
giudicare le persone dall'aspetto; la segnalazione corrispondente ora è «molestie o
comportamenti che mettono a disagio».

### Segnalazioni
Usano i 10 tipi del brief (sezione 8: poca luce, lampione guasto, strada deserta, angoli
nascosti, luogo isolato, molestie, incuria, marciapiede, fermata, luogo positivo), la fascia
oraria e un voto facoltativo da 1 a 5. **Niente testo libero e niente dati identificativi**,
come chiede il brief; genere e fascia d'età si allegano solo se la persona lo sceglie in
«Aiuta la mappa». L'app spiega che un tratto cambia colore solo dopo 5 segnalazioni dello
stesso tipo. Per ora restano sul telefono: partiranno con l'API della fase 5.

### Supporto
Restano 112, 113, 118, 115, 1522, il sito ufficiale del 1522 e l'albo degli psicologi. Ho
**tolto le ricerche su Google Maps dei centri antiviolenza**: il brief vieta di localizzare
strutture di accoglienza per donne, «nemmeno come punti di aiuto». Il 1522 mette comunque in
contatto con il centro più vicino. Per lo stesso motivo la ricerca dell'app esclude strutture
sociali e nomi come «antiviolenza», «rifugio», «accoglienza».

### Accessibilità
Testo più grande, tema chiaro/scuro (anche automatico), indicazioni a voce facoltative,
pulsanti di almeno 44 px, etichette per i lettori di schermo, animazioni ridotte se il
sistema lo chiede. I colori delle strade sono sempre accompagnati da testo (metri con
criticità, percentuali, motivo del tratto) per chi distingue male rosso e verde.

## Limiti di questa versione

- **Posizione**: nell'anteprima pubblicata su claude.ai il GPS non è disponibile: si sceglie
  la partenza sulla mappa e la navigazione parte in **simulazione** (utile anche in demo).
  Dal file aperto con localhost o https il GPS funziona.
- **Ore**: i parametri che cambiano con l'ora (persone, negozi aperti, aiuto, mezzi) sono
  precalcolati per le 24 ore di un mercoledì e di un sabato di novembre; fascia, tramonto e
  tipo di giorno (feriale, weekend, festivi, venerdì sera) sono invece quelli della data vera.
- **Edifici**: OSM ha l'altezza per meno dell'1% degli edifici di Vicenza; le altezze del 3D
  sono indicative (per tipo di edificio e superficie) e non entrano nel punteggio.
- **Ricerca**: vie, piazze e luoghi con nome, senza numeri civici.
- **Condivisione della posizione**: manda un link con il punto attuale, non un tracciamento
  continuo (servirebbe un server).
- **Segnalazioni, percorsi e note** restano sul telefono finché non c'è l'API.

## Da decidere insieme

1. **Domande sul genere e sulle situazioni.** Servono ai pesi del modello, ma sono dati
   delicati. In alternativa si potrebbero chiedere solo preferenze dirette («quanto conta per
   te la luce?»), senza identità. Proposta: tenerle facoltative come ora e validarle con il
   questionario.
2. **Persona non binaria → pesi del profilo LGBTQ+.** È una mia scelta, da confermare.
3. **Percentuale di strade verdi nella home.** Di sera, in tutta la città, le strade verdi
   sono poche (molte sono di campagna). Ora la home mostra «verdi o gialle» e la ripartizione
   completa; si può anche limitare al quartiere della persona.
4. **Mascotte**: «Lumi ragazza» e «Lumi ragazzo» sono la guida, non il genere di chi usa
   l'app. Se volete, una terza guida non caratterizzata.
5. **Codice di protezione**: oggi è facoltativo. Chi lavora sui temi della violenza potrebbe
   consigliare di renderlo più visibile, o di aggiungere un'uscita rapida dall'app.
6. Il brief diceva che l'interfaccia per gli utenti l'avrebbero fatta altri: questa è una
   base completa ma va rivista da chi ha disegnato la demo.
