# Dati dimostrativi (simulati)

Questa cartella contiene **solo scenari simulati** per la demo dell'hackathon.
Non sono dati reali e la pipeline non li usa mai da sola: entrano nei calcoli solo
con l'opzione esplicita `--demo` (o `demo=True`), e ogni risultato calcolato con
essi riporta `scenario_demo: true`.

| File | Contenuto | Da sostituire con |
|---|---|---|
| `eventi_demo.csv` | tre eventi serali inventati in luoghi reali (Teatro Comunale, Basilica Palladiana, Campo Marzo), per mostrare l'effetto degli eventi sul punteggio | eventi veri del Comune in `data/manual/eventi.csv` (stesse colonne), vedi `docs/piano_dati_reali.md` |
