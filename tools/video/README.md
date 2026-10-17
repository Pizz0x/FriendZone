# Video della demo

Due video per la presentazione (sezione 3, «Cosa e come, con demo»), da usare se il telefono
o la rete non collaborano. Sono già in `video/`:

| File | Cosa mostra | Durata |
|---|---|---|
| `demo_app.mp4` | l'app sul telefono, con i passi della demo scritti a fianco (16:9) | 24 s |
| `demo_app_verticale.mp4` | solo lo schermo del telefono, senza testi (per una slide con una cornice propria, 780×1688) | 24 s |
| `demo_enti.mp4` | `enti.html` per il Comune, con le didascalie in alto a destra (16:9) | 24 s |
| `demo_enti_senza_didascalie.mp4` | lo stesso senza didascalie | 24 s |

Sono H.264 a 30 fps senza audio (1920×1080 tranne quello verticale): si inseriscono in
PowerPoint, Keynote e Google Slides. Si possono commentare a voce con il testo del discorso.

## Cosa succede nei video

**App** (sabato 17 ottobre 2026, ore 22:00, profilo «donna», domande iniziali già fatte):
home → «Mappa» nella barra in basso → «Prova di sera: Stazione → Corso Fogazzaro» → i due percorsi
(consigliato 16 min senza tratti rossi, più breve 15 min con 239 m di criticità percepite)
→ si tocca il più breve e poi di nuovo il consigliato → «Avvia», il navigatore va per
6 secondi → SOS con 112 e 1522. Senza GPS il navigatore va in simulazione (lo dice
l'etichetta «Simulazione»); l'avviso che lo spiega è nascosto.

**Comune** (giorno feriale, donna 35–74): tutta la città alle 11 → l'ora trascinata da 11 a
22, le strade cambiano colore → i quartieri con S medio più basso → zoom su stazione e
Campo Marzo → clic sul tratto rosso che l'app faceva evitare, con punteggio e parametri.

## Rifarli

Servono Node.js con Playwright (e il suo Chromium) e ffmpeg; serve internet per MapLibre,
Leaflet e i caratteri. Dalla cartella principale:

```bash
npm install playwright      # se non c'è già (oppure NODE_PATH=$(npm root -g) con l'installazione globale)
node tools/video/app.js     # ~5 minuti
node tools/video/enti.js    # ~10 minuti
```

La pagina gira con un orologio finto e ogni fotogramma viene catturato solo quando è
pronto, quindi il video è fluido anche su un computer lento o senza scheda grafica.
I numeri delle didascalie (minuti, metri, km in rosso, quartieri) sono letti dalla pagina
durante la registrazione: se i dati cambiano, le didascalie seguono. Lo script si ferma
con un errore se il percorso della demo non è più alle 22:00 o se il tratto del Campo
Marzo non è più rosso. I file intermedi restano in `video/.build/` (ignorata da git).
