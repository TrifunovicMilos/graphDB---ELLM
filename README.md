# Operatori semantici su grafi: dominio *games* (Oxigraph)

Progetto di gruppo del corso *Graph Databases* 2026/2027
Dominio: videogiochi con serie. Motore: **Oxigraph** (libreria Python `pyoxigraph`). Gruppo: **[ELLM]**.

## In breve

Il progetto esegue query SPARQL su un grafo di videogiochi e, dentro la query, chiede a un modello di linguaggio (LLM) di decidere su ogni riga: è un *operatore semantico*. Ci sono quattro operatori:

| Operatore | Cosa fa | Query comuni |
|---|---|---|
| `sem_filter` | sì/no su una riga | Q1, Q2, Q3 |
| `sem_classify` | sceglie una etichetta tra 8 | Q4 |
| `sem_map` | estrae un testo libero, poi lo abbina a un'entità | Q5 |
| `sem_join` | sì/no su una coppia (gioco, serie) | Q6, Q7 |

Tutto il lavoro misura qualità (precision, recall, accuracy...) e costo (numero di chiamate al modello) contro le soluzioni ufficiali del corso.

Per ora tutto gira anche con un **modello finto** (una regola a parole chiave, gratuito e istantaneo) che serve a collaudare la struttura senza aspettare il modello vero.

## Stato del lavoro

| Query | Stato | Note |
|---|---|---|
| Q1 filtro "platformer" | fatta | provata col modello vero su 60 giochi |
| Q2 filtro "visual novel" | fatta | provata solo col modello finto |
| Q3 restrizione + filtro | fatta, 2 piani | `q3_struttura_prima`, `q3_semantica_prima` (vedi sotto) |
| Q4 classificazione | fatta | provata col modello vero su 20 giochi |
| Q5 estrazione | fatta (abbinamento semplice) | provata col modello vero su 15 giochi |
| Q6 join 50 × 100 | **manca** | |
| Q7 join grande (facoltativa) | **manca** | |
| Q8 conteggio per decennio | fatta | richiede Q1 su tutti i 1.000 giochi |

## Cosa manca

- `sem_join` per Q6 (ciclo annidato, 5.000 coppie) e, se vogliamo il bonus, Q7 con blocking top-10 e embedding (`bge-small-en-v1.5`).
- Il **modello veloce** (gateway del corso, o altro): in locale il modello da 3 miliardi di parametri impiega circa 15 secondi a chiamata, quindi i run completi (circa 8.700 chiamate sul dev, circa 19.900 sull'eval) non sono fattibili sui nostri portatili.
- I **file di run** (`runs/<dominio>/<set>/<query>/<run_id>.json`) e il controllo con `tools/semops_check.py` del pacchetto dati. Il controllore si aspetta per Q1-Q6 un run con piano `ref` (riferimento) anche sul set di valutazione.
- Il **baseline** (piano di riferimento: una richiesta per riga o coppia, senza trucchi) per Q1-Q6, sul dev e sull'eval, e il confronto con i piani ottimizzati.
- Le **ottimizzazioni**: la cache c'è già; mancano cascata (con confidenza), blocking, ecc.
- Una τ migliore (adesso è solo nome + lead) e istruzioni migliori nel prompt; analisi degli errori.
- Le **6 query nostre** (M2) con soluzione e controllo di leakage, e la nota di design / report.
- Q5: abbinamento più furbo (oggi: nome identico, una sola entità, altrimenti "non risolto").

## Struttura del repository

```
.
├── README.md
├── .gitignore
├── semops.py        libreria: caricamento grafo, τ, prompt, modello finto e vero, cache,
│                    sem_filter, sem_classify, esecuzione query, valutazioni (Q1-Q4, Q8)
├── estrazione.py    Q5: sem_map e abbinamento stringa -> entità (labels.csv, aliases.csv)
├── run.py           il programma da lanciare (vedi "Come si usa")
├── query/
│   ├── q1.rq   q2.rq   q4.rq   q5.rq
│   └── q3_struttura_prima.rq   q3_semantica_prima.rq
├── data/games/      NON è nel repository: pacchetto dati del corso (dev/ ed eval/)
└── cache_llm.json   generato dal programma, NON è nel repository
```

## Installazione

1. **Python 3** (provato con 3.12) e la libreria `pyoxigraph`:
   ```bash
   pip install pyoxigraph
   ```
2. **Dati**: copia il pacchetto del corso in `data/games/` senza cambiare i nomi dei file. Per questo progetto servono almeno `data/games/dev/graph.nt`, `labels.csv`, `aliases.csv` e la cartella `gt/`. Non va messo su Git (credo)
3. **Modello locale (facoltativo, per `--llm vero`)**: installa [Ollama](https://ollama.com) e scarica un modello piccolo:
   ```bash
   ollama pull qwen2.5:3b
   ```
   Ollama deve essere acceso mentre lanci i run. Indirizzo e nome del modello sono in cima a `semops.py` (`URL`, `MODELLO`).

## Come si usa

Dalla cartella del progetto:

```bash
python run.py <file_query> [--tipo filtro|classifica|estrai] [--n N] [--llm finto|vero]
              [--dati cartella] [--gt file_soluzione] [--q8 file_q8]
```

| Opzione | Significato |
|---|---|
| `--tipo` | `filtro` (Q1-Q3, default), `classifica` (Q4), `estrai` (Q5) |
| `--n N` | usa solo i primi N giochi (0 = tutti) |
| `--llm` | `finto` (default, gratis) oppure `vero` (Ollama; usa e riempie la cache) |
| `--dati` | cartella del set, default `data/games/dev` (per l'eval: `data/games/eval`) |
| `--gt` | soluzione ufficiale: calcola precision/recall (o hit rate, accuracy, ...) |
| `--q8` | solo con Q1 su tutti i giochi: calcola anche il conteggio per decennio |

Esempi, tutti col modello finto (aggiungi `--llm vero --n 20` per provare quello vero):

```bash
python run.py query/q1.rq --gt data/games/dev/gt/q1.csv --q8 data/games/dev/gt/q8.csv
python run.py query/q2.rq --gt data/games/dev/gt/q2.csv
python run.py query/q3_struttura_prima.rq --gt data/games/dev/gt/q3.csv
python run.py query/q3_semantica_prima.rq --gt data/games/dev/gt/q3.csv
python run.py query/q4.rq --tipo classifica --gt data/games/dev/gt/q4.csv
python run.py query/q5.rq --tipo estrai --gt data/games/dev/gt/q5.csv
```

Consigli:
- L'output elenca ogni gioco valutato: aggiungi `| tail -30` per vedere solo il riassunto.
- Con `--llm vero` e più di 100 giochi il programma chiede conferma (ore di attesa).
- Le risposte vere si salvano in `cache_llm.json`: rilanciare lo stesso comando non rifà le chiamate. La chiave della cache include modello e prompt, quindi se cambi τ, le istruzioni o il modello le risposte vecchie non vengono riusate.

## Le query comuni, in breve

Il criterio ℓ di ogni query è **fisso** e identico per tutti i gruppi (compare nel `.rq` tra virgolette). Sono nostri: le istruzioni intorno, τ, il piano di esecuzione e il modello. Numeri sul set dev (1.000 giochi nel set principale).

- **Q1** `the game is a platformer`: filtro su 1.000 giochi. Soluzione espansa: genere che arriva a *platformer* anche attraverso i sottogeneri (200 giochi); soluzione diretta: 171.
- **Q2** `the game is a visual novel`: filtro raro (30 positivi). Le descrizioni spesso nominano già il genere, quindi la gestione dei testi in τ conta.
- **Q3**: prima una restrizione strutturale (giochi con uno sviluppatore, `P178`, il cui paese, `P17`, è il Giappone: 259 giochi in 272 righe), poi il filtro di Q1. 2 piani:
  - `q3_struttura_prima`: prima i 259 giochi unici, poi il filtro (259 chiamate);
  - `q3_semantica_prima`: prima il filtro su tutti i 1.000, poi la restrizione (1.000 chiamate).
  Il risultato è lo stesso, cambia il costo. Le metriche ufficiali contano le chiamate dei due ordini.
- **Q4** `the genre that describes the game best`: classificazione di 444 giochi in una di 8 etichette (action, adventure, role-playing, action-adventure, puzzle, racing, first-person shooter, shoot 'em up). Una risposta fuori dalle 8 è un errore, registrato a parte. Metriche: hit rate, accuracy e macro-F1.
- **Q5** `the company that developed the game`: il modello risponde con un nome; lo abbiniamo a un'entità tramite `labels.csv` e `aliases.csv`. Si valutano solo i 805 giochi con soluzione. Metriche: accuracy e tasso di non risolti.
- **Q6** `the game is part of the series`: join di 50 giochi per 100 serie (5.000 coppie, tutte da valutare nel piano di riferimento). *Da fare.*
- **Q7** (facoltativa): come Q6 ma 200 × 300, con blocking top-10 prima del modello. *Da fare.*
- **Q8**: conteggio, per decennio di `ex:firstYear`, delle decisioni di Q1, senza nuove richieste. Metrica: errore relativo medio sui decenni non vuoti.

## Come funziona

```
run.py
 ├─ carica il grafo (graph.nt) in Oxigraph
 ├─ esegue la query una prima volta con un operatore che dice sempre "vero" (costo zero)
 │    per sapere quali giochi arrivano al modello ("candidati")
 └─ esegue la query vera: per ogni riga Oxigraph chiama la nostra funzione sem_*:
        τ(riga) -> testo  ->  prompt (istruzioni + "Criterion: ℓ" + testo)
        -> cache?  sì: risposta salvata   no: chiamata al modello (Ollama) e salvataggio
    poi confronta con gt/*.csv e stampa le metriche
```

Dove cambiare le cose (in `semops.py` salvo dove indicato):
- **cosa vede il modello**: funzione `tau`
- **come gli si chiede**: `ISTRUZIONI`, `ISTRUZIONI_CLASSIFICA`, `costruisci_prompt*` (per Q5: `estrazione.py`)
- **il modello**: `MODELLO` e `URL`
- **l'ordine di valutazione**: i file `.rq` (le sottoquery `{ SELECT ... }` fanno da "barriera": si calcolano prima del filtro semantico)

## Risultati provvisori (solo per capire che funziona)

Campioni piccoli e modello locale da 3 miliardi di parametri: non sono risultati da riportare.

- Q1, 60 giochi: precision 0.71 / recall 0.62 sulla soluzione diretta; 0.86 / 0.55 sulla espansa.
- Q4, 20 giochi: hit rate 0.65, macro-F1 0.68; 3 risposte su 20 fuori dall'elenco delle etichette.
- Q5, 15 giochi (13 valutabili): accuracy 0.69.
- Q5 col modello finto su tutto il dev: accuracy 0.34, non risolti 0.63 (il finto cerca solo "developed by X").

## Decisioni e dubbi aperti

- **P178 (sviluppatore) in τ**: nel catalogo delle proprietà è ammessa in τ, ma è la soluzione di Q5. Per ora τ non la usa. Da confermare con le slide del progetto.
- **Testo di τ**: usiamo `ex:lead` come arriva in `graph.nt`; manca il confronto con la colonna `description_screened` di `entities.csv`.
- **Q5, abbinamento**: l'abbinamento a nome identico scarta i nomi ambigui; il modello a volte risponde con la casa madre ("Sega") invece dello studio ("Sega AM2").
- **Risposte fuori elenco in Q4**: il modello piccolo inventa etichette (es. "metroidvania game"). Opzioni da valutare: istruzione più severa, formato di risposta vincolato, modello più grande.
- **Cache e costi**: non sappiamo ancora come le risposte in cache vengano contate nei costi ufficiali (il file di run ha un campo `cache_hit` per ogni chiamata).

