# FRIENDlyZONE, l'app per chi cammina

Il progetto ha due interfacce, generate dagli stessi dati con `python -m pipeline.frontend`:

| | Per chi | Cosa fa | File |
|---|---|---|---|
| **Mappa per gli enti** | Comune, pari opportunità, mobilità | tutte le strade colorate per ora, giorno, meteo e profilo; parametri di ogni tratto; quartieri con S più basso | `frontend/enti.html` |
| **App FRIENDlyZONE** (guida: Lumi) | cittadine e cittadini | domande iniziali, mappa 3D, percorso consigliato e navigatore, SOS, segnalazioni, supporto, diario | `frontend/app.html` |

`frontend/index.html` porta a tutte e due. Le pagine non hanno bisogno di un server: i dati
(13.728 tratti, parametri per le 24 ore di un feriale e di un sabato, edifici, vie e luoghi
per la ricerca) sono dentro il file. Serve internet solo per la libreria della mappa
(MapLibre) e i caratteri. Per usare il GPS del telefono la pagina va aperta da https o da
localhost:

```bash
python -m http.server -d frontend 8000   # poi http://localhost:8000/app.html
```

## Da dove parte

L'app riprende la demo del team «Lumi» (nome, mascotte, colori, schermate, barra in basso,
diario, condivisione della posizione) e la collega al modello del backend.

| Nella demo | Nell'app |
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
diceva il contrario. Ora **l'SOS non chiede mai il codice**: mostra subito 112 e 1522
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

## Seconda revisione (16/10, sera)

Su richiesta del team:

- **Nome e logo**: l'app si chiama FRIENDlyZONE. Il simbolo del logo è ritagliato con la
  trasparenza (`frontend/assets/brand/mark.webp`), la scritta è testo (Montserrat) con i tre
  colori delle strade. Lumi resta il nome della guida.
- **Percorso sempre visibile**: è disegnato sopra gli edifici, con un bordo (viola di giorno,
  verde lime di notte); l'inquadratura usa solo la parte di mappa libera dai pannelli.
- **Mappa più chiara**: di notte la mappa è grigia (non più quasi nera) e gli edifici sono
  più chiari e un po' trasparenti; di giorno strade più larghe.
- **Tutto nello schermo**: illustrazioni e spaziature si adattano all'altezza del telefono;
  i pulsanti sopra la mappa vanno a capo invece di uscire dallo schermo; il pannello in
  basso non copre mai i pulsanti. Provato su 320×568, 360×640, 375×667, 390×844,
  412×915, 430×932, in orizzontale e su desktop.
- **Mascotte nitida**: le illustrazioni sono state ingrandite 3 volte con un modello per
  disegni (Real-ESRGAN anime) dopo aver tolto l'alone chiaro del vecchio ritaglio
  (`tools/upscale_mascots.py`).
- **SOS** sempre in vista: in alto sulla mappa e nella barra del navigatore.

### Errori corretti
Trovati con una revisione del codice e con un collaudo automatico di tutte le schermate:

- l'SOS e le segnalazioni usavano la posizione della **simulazione** invece di quella vera:
  ora solo il GPS; senza GPS l'app lo dice e propone di chiamare la persona di fiducia;
- dopo il primo viaggio i percorsi non si ricalcolavano più cambiando ora, pioggia o
  compagnia; uscendo dal navigatore la simulazione poteva restare attiva;
- con la posizione GPS il percorso non partiva se la destinazione era già scelta, o se i
  dati non avevano finito di caricare;
- percorsi su anelli chiusi disegnati dalla parte sbagliata; tratti di lunghezza zero
  all'inizio o alla fine davano indicazioni sbagliate («gira a destra» negli ultimi metri);
- con il GPS, un salto del segnale poteva far saltare istruzioni o dichiarare l'arrivo in
  anticipo: ora la posizione si cerca solo poco prima e poco dopo il punto raggiunto;
- nomi di vie o luoghi con caratteri speciali potevano rompere la pagina (ora sono
  protetti, anche nella mappa per gli enti);
- il codice di protezione si poteva cambiare senza conoscere il vecchio; senza https veniva
  salvato in chiaro; ora c'è anche una pausa dopo 5 tentativi sbagliati;
- l'ora di partenza usava il fuso del telefono invece di quello di Vicenza;
- la mappa non aveva un pulsante per tornare indietro; il pannello dei messaggi non si
  chiudeva con Esc e non era accessibile ai lettori di schermo; gli interruttori non
  dicevano se erano accesi;
- «Cancella tutti i miei dati» lasciava in memoria percorso, destinazione e scelte;
- aprendo un pannello (ora, SOS, legenda) il browser spostava in alto tutta l'app per
  mettere a fuoco il primo pulsante, e dopo la chiusura la schermata restava spostata;
- con partenza uguale alla destinazione, o un punto lontano dalle strade, il pannello
  restava su «Calcolo il percorso…»: ora dice cosa non va;
- con due percorsi entrambi senza tratti rossi il testo diceva «evita 0 m di tratti rossi»;
- in orizzontale l'app era incorniciata come su desktop e la barra in basso finiva fuori
  posto: ora usa tutta la larghezza, con i pannelli ai lati e la mappa al centro.

Collaudo automatico (Playwright) su 320×568, 360×640, 375×667, 390×844, 430×932, 667×375,
844×390 e 1280×720: tutte le schermate dal benvenuto all'arrivo, senza errori JavaScript,
senza contenuti fuori dallo schermo in orizzontale e con l'SOS sempre raggiungibile. Più i
casi limite: codice errato 5 volte, condivisione senza GPS o senza contatti, ricerche vuote,
telefono con un altro fuso orario, ricalcolo dopo una navigazione, ricarica della pagina.

La condivisione della posizione ora è dichiaratamente **un link una tantum** (la posizione
di quel momento): la barra «posizione condivisa» faceva pensare a un tracciamento continuo,
che senza un server non c'è.

## Terza revisione (17/10)

- **Giorno e notte a scelta**: in Impostazioni, «Aspetto giorno o notte» vale per l'app e
  per la mappa insieme: *segue il sole* (predefinito: chiaro di giorno, scuro dopo il
  tramonto), *sempre giorno*, *sempre notte*, *come il telefono*. Sulla mappa c'è un
  pulsante sole/luna per passare al volo. Con «segue il sole» la mappa segue l'ora scelta
  per il percorso (se pianifichi le 22, la mappa diventa notturna).
- **SOS della barra in basso**: icona e scritta ora sono centrate nel pulsante.
- **Variante grafica «Lanterna»** (`frontend/app-lanterna.html`), da confrontare in gruppo.
  Stesso codice e stesse funzioni: cambia solo lo strato di stile
  (`frontend/src/themes/lanterna.css` e `.json`), quindi ogni correzione vale per tutte e due.
  L'idea è la segnaletica urbana e la luce dei lampioni:
  - giallo lampione per le azioni, l'antracite del logo per testi e contorni;
  - schede con contorno pieno e ombra netta, come adesivi; pulsanti che «si premono»;
  - titoli in Bricolage Grotesque, testi in Atkinson Hyperlegible (carattere disegnato per
    chi vede poco);
  - la guida Lumi dentro l'alone di un lampione, il reticolo di strade del logo come motivo
    nelle prime schermate, barra in basso scura con il tasto SOS rosso quadrato;
  - sulla mappa il percorso è antracite con bordo bianco di giorno, bianco di notte.
  Per aggiungere altre varianti basta un nuovo `themes/<nome>.css` + `.json`: la pipeline
  genera `frontend/app-<nome>.html`.

## Deciso con il team

- Domande su genere e situazioni personali: **sì**, facoltative come ora.
- Persona non binaria → pesi del profilo LGBTQ+: **sì**.

## Ancora da decidere

1. **Percentuale di strade verdi nella home.** Di sera, in tutta la città, le strade verdi
   sono poche (molte sono di campagna). Ora la home mostra «verdi o gialle» e la ripartizione
   completa; si può anche limitare al quartiere della persona.
2. **Mascotte**: «Lumi ragazza» e «Lumi ragazzo» sono la guida, non il genere di chi usa
   l'app. Se volete, una terza guida non caratterizzata.
3. **Codice di protezione**: oggi è facoltativo. Chi lavora sui temi della violenza potrebbe
   consigliare di renderlo più visibile, o di aggiungere un'uscita rapida dall'app.
