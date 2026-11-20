# Libreria del progetto importata da run.py
# da run.py le funzioni si chiamano con semops.nome_funzione(...)

# INDICE: dati, tau e prompt, modello finto,  modello vero + cache
#         sem_filter (Q1-Q3), sem_classify (Q4), esegui e valuta, Q8
import csv, hashlib, json, os, time, urllib.request
import pyoxigraph as ox

# costanti (usate in questo file)
URL        = "http://localhost:11434/v1/chat/completions"             # indirizzo di Ollama sul tuo Mac
MODELLO    = "qwen2.5:3b"                                             # modello da usare (anche nella chiave di cache)
FILE_CACHE = "cache_llm.json"                                         # cache
EX         = "http://example.org/semop/"                              # prefisso dei nostri predicati (ex:)
XSD_BOOL   = ox.NamedNode("http://www.w3.org/2001/XMLSchema#boolean") # tipo booleano per SPARQL

# le 8 etichette di Q4 per i giochi: codice -> nome in inglese
ETICHETTE_Q4 = {
    "Q270948":  "action game",
    "Q23916":   "adventure video game",
    "Q744038":  "role-playing video game",
    "Q343568":  "action-adventure game",
    "Q54767":   "puzzle video game",
    "Q860750":  "racing video game",
    "Q185029":  "first-person shooter",
    "Q1044478": "shoot 'em up",
}
# nome (minuscolo) -> codice, per capire a quale etichetta corrisponde la risposta del modello
NOME_A_QID = {nome.lower(): qid for qid, nome in ETICHETTE_Q4.items()}

# contatori condivisi
stats = {"chiamate": 0, "cache": 0, "secondi": 0.0, "fuori_lista": 0, "non_valide": 0}

# chiamata da run.py subito prima della query vera
def azzera_stats():
    stats.update(chiamate=0, cache=0, secondi=0.0, fuori_lista=0, non_valide=0)

# DATI

# legge un file .nt e lo carica in un database Oxigraph in memoria
def carica_grafo(percorso):
    store = ox.Store()
    store.bulk_load(path=percorso, format=ox.RdfFormat.N_TRIPLES)
    return store

# TAU E PROMPT

ISTRUZIONI = ("You are a classifier. Decide whether the item satisfies the criterion. "
              "Answer only with JSON: {\"answer\": true} or {\"answer\": false}.")

ISTRUZIONI_CLASSIFICA = ("You are a classifier. Choose the single label that best answers the criterion "
                         "for the item. Answer only with JSON: {\"label\": \"<one of the labels>\"}.")

# trasforma un'entità (qui: nome + lead) in un testo (il modello vede solo testo)
# tau("Doom", "Doom is a 1993 first-person shooter.") ->  "Doom. Doom is a 1993 first-person shooter."
# il [:1200] taglia il testo ai primi 1200 caratteri
def tau(label, lead):
    return (label + ". " + lead)[:1200]

# incolla istruzioni + criterio + tau nel messaggio completo per il modello
# la chiama sem_filter per ogni riga
# la struttura del prompt è: istruzioni, 'Criterion: ...', tau
def costruisci_prompt(criterio, testo_tau):
    return ISTRUZIONI + "\n\nCriterion: " + criterio + "\n\nItem: " + testo_tau

# prompt per la CLASSIFICAZIONE: come sopra più l'elenco delle etichette ammesse
def costruisci_prompt_classifica(criterio, testo_tau, nomi):
    return (ISTRUZIONI_CLASSIFICA + "\n\nCriterion: " + criterio +
            "\n\nLabels: " + ", ".join(nomi) + "\n\nItem: " + testo_tau)


# "MODELLO FINTO (gratis)

# dice True se nel testo dopo 'Item:' compare una parola scelta dal criterio
# lanci run.py con --llm finto
def llm_finto(prompt):
    stats["chiamate"] += 1
    criterio = prompt.split("Criterion:")[1].split("Item:")[0].lower()
    testo = prompt.split("Item:")[1].lower()
    parola = "visual novel" if "visual novel" in criterio else "platform"
    return parola in testo

# finto LLM per la classificazione: sceglie un'etichetta da parole chiave nel testo
# lanci run.py con --tipo classifica --llm finto.
# guarda il testo dopo 'Item:'
# se non trova nulla risponde "action game".
def llm_finto_etichetta(prompt):
    stats["chiamate"] += 1
    testo = prompt.split("Item:")[1].lower()
    regole = [("first-person shooter", "first-person shooter"),
              ("shoot 'em up", "shoot 'em up"), ("shmup", "shoot 'em up"),
              ("role-playing", "role-playing video game"),
              ("puzzle", "puzzle video game"), ("racing", "racing video game"),
              ("action-adventure", "action-adventure game"),
              ("adventure", "adventure video game"), ("action", "action game")]
    for parola, etichetta in regole:
        if parola in testo:
            return etichetta
    return "action game"


# MODELLO VERO (Ollama) E CACHE

if os.path.exists(FILE_CACHE):
    with open(FILE_CACHE, encoding="utf-8") as f:
        cache = json.load(f)
else:
    cache = {}

# manda un prompt a Ollama e restituisce True/False (o None se la risposta è rotta)
# la chiama solo llm_vero, e solo se la risposta NON è già in cache
def chiama_modello(prompt, campo, tipo):
    stats["chiamate"] += 1
    # corpo della richiesta, temperature 0 (stessa domanda -> stessa risposta)
    corpo = {"model": MODELLO, "temperature": 0,
             "messages": [{"role": "user", "content": prompt}],
             "response_format": {"type": "json_object"}}
    # json.dumps = dizionario -> stringa JSON;  .encode() = stringa -> byte
    richiesta = urllib.request.Request(URL, data=json.dumps(corpo).encode(),
                                       headers={"Content-Type": "application/json"})
    start = time.time()
    with urllib.request.urlopen(richiesta, timeout=300) as r:   # invia e aspetta (max 300 s)
        risposta = json.loads(r.read())                         # byte -> dizionario
    stats["secondi"] += time.time() - start
    # risposta ha forma {"choices": [{"message": {"content": '{"answer": true}'}}], ...}
    testo = risposta["choices"][0]["message"]["content"]        # stringa '{"answer": true}'
    try:
        valore = json.loads(testo)[campo]                       # -> True
        if isinstance(valore, tipo):                            # es. un vero True/False, non "false"
            return valore
    except Exception:
        pass
    print("   !! risposta non valida:", testo)
    stats["non_valide"] += 1
    return None             # None = "risposta rotta": NON si salva in cache

# prima guarda la cache, se non c'è chiede al modello e salva.
def _risposta_con_cache(prompt, campo, tipo):
    chiave = hashlib.sha256((MODELLO + "\n" + prompt).encode()).hexdigest()
    if chiave in cache:                      
        stats["cache"] += 1
        return cache[chiave]
    risposta = chiama_modello(prompt, campo, tipo)
    if risposta is None:
        return None
    cache[chiave] = risposta
    with open(FILE_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f)                   
    return risposta

# la chiama sem_filter per ogni riga, se lanci con --llm vero
def llm_vero(prompt):
    risposta = _risposta_con_cache(prompt, "answer", bool)
    return False if risposta is None else risposta

# la chiama sem_classify per ogni riga, se lanci con --tipo classifica --llm vero
def llm_vero_etichetta(prompt):
    return _risposta_con_cache(prompt, "label", str)


# sem_filter (Q1-Q3)

# trasforma true/false di Python nel valore booleano di SPARQL, l'unico che la FILTER capisce
# _bool(True) -> "true"^^xsd:boolean
def _bool(valore):
    return ox.Literal("true" if valore else "false", datatype=XSD_BOOL)

def crea_funzioni(llm):
    def sem_filter(label, lead, criterio):
        ok = llm(costruisci_prompt(criterio.value, tau(label.value, lead.value)))
        print(f"  [chiamate {stats['chiamate']}, cache {stats['cache']}] {label.value}: {ok}")
        return _bool(ok)     # dai la risposta alla FILTER
    
    # il dizionario dice a Oxigraph: "quando vedi ex:sem_filter, chiama questa funzione"
    return {ox.NamedNode(EX + "sem_filter"): sem_filter}

# sem_filter dice sempre vero e non costa nulla
# run.py la usa nel passo 1 per sapere quali giochi arrivano alla FILTER (i candidati) senza interrogare nessun modello
def funzioni_sempre_vero():
    def sem_filter(label, lead, criterio):
        return _bool(True)
    return {ox.NamedNode(EX + "sem_filter"): sem_filter}


# sem_classify (Q4)

# per confrontare le etichette: toglie spazi e punto finale, tutto minuscolo
def normalizza(testo):
    return testo.strip().rstrip(".").lower()

def crea_funzioni_classifica(llm):
    nomi = list(ETICHETTE_Q4.values())
    def sem_classify(label, lead, criterio):
        prompt = costruisci_prompt_classifica(criterio.value, tau(label.value, lead.value), nomi)
        risposta = llm(prompt)
        if risposta is None:                         # risposta rotta (già contata in non_valide)
            risposta = ""
        elif normalizza(risposta) not in NOME_A_QID:
            stats["fuori_lista"] += 1
        print(f"  [chiamate {stats['chiamate']}, cache {stats['cache']}] {label.value}: {risposta!r}")
        return ox.Literal(risposta)
    return {ox.NamedNode(EX + "sem_classify"): sem_classify}

# sem_classify che restituisce stringa vuota e non costa nulla (per vedere i candidati)
def funzioni_classifica_vuote():
    def sem_classify(label, lead, criterio):
        return ox.Literal("")
    return {ox.NamedNode(EX + "sem_classify"): sem_classify}


# ESEGUIRE UNA QUERY E VALUTARE

# da indirizzo completo a codice breve
# la chiama esegui per ogni riga del risultato
# qid(NamedNode("http://www.wikidata.org/entity/Q101243107")) -> "Q101243107"
# nodo.value = il testo dell'indirizzo; 
# rsplit("/", 1) lo taglia dall'ultimo "/" in due pezzi; [-1] prende l'ultimo pezzo
def qid(nodo):
    return nodo.value.rsplit("/", 1)[-1]

# legge il .rq e sostituisce "LIMIT __N__" con "LIMIT 60" (se n=60) o lo toglie (n=0)
def _leggi_query(file_query, n):
    with open(file_query, encoding="utf-8") as f:
        q = f.read()
    return q.replace("LIMIT __N__", ("LIMIT " + str(n)) if n else "")

# esegue una query e restituisce {codice_gioco: nome}
# run.py la chiama prima con funzioni_sempre_vero (candidati), poi con crea_funzioni(llm)
# 1. legge il testo della query dal file
# 2. sostituisce "LIMIT __N__" con "LIMIT 60" (se n=60) oppure lo toglie (n=0)
# 3. store.query(...) esegue la query; 
# 4. ogni riga (binding) ha ?e e ?label: riga["e"] -> indirizzo, riga["label"] -> nome
def esegui(store, file_query, n, funzioni):
    q = _leggi_query(file_query, n)
    return {qid(r["e"]): r["label"].value
            for r in store.query(q, custom_functions=funzioni)}

def esegui_classifica(store, file_query, n, funzioni):
    q = _leggi_query(file_query, n)
    risultati = {}
    for r in store.query(q, custom_functions=funzioni):
        genere = r["genre"]
        risultati[qid(r["e"])] = genere.value if genere is not None else ""
    return risultati

# confronta le risposte del modello con la soluzione ufficiale
# run.py la chiama solo se hai scritto --gt <file>
# candidati  {qid: nome} di tutti i giochi valutati
# predetti   {qid: nome} di quelli per cui il modello ha detto True
# se i veri platformer sono A, B, C e il modello dice A, B, D:
# giusti = A, B | falso positivo = D | falso negativo = C
# precision = giusti / trovati = 2/3,  recall = giusti / positivi veri = 2/3
def valuta(file_gt, candidati, predetti):
    with open(file_gt, encoding="utf-8") as f:
        # DictReader: ogni riga del CSV diventa un dizionario con le intestazioni come chiavi
        # gt = {"Q170003": {"qid": "Q170003", "direct": "1", "path": "1"}, ...}
        gt = {riga["qid"]: riga for riga in csv.DictReader(f)}
    for colonna in ("direct", "path"):          # lo stesso confronto, due volte
        giusti, fp, fn = [], [], []
        for codice in candidati:
            if codice not in gt:
                print("ATTENZIONE: non in", file_gt, ":", codice)
                continue
            vero = gt[codice][colonna] == "1"
            dice_si = codice in predetti
            if dice_si and vero:
                giusti.append(codice)
            elif dice_si and not vero:
                fp.append(codice)
            elif vero:
                fn.append(codice)
        trovati = len(giusti) + len(fp)
        positivi = len(giusti) + len(fn)
        prec = len(giusti) / trovati if trovati else 0.0
        rec = len(giusti) / positivi if positivi else 0.0
        print(f"\nconfronto con '{colonna}': positivi veri {positivi} | trovati {trovati} | giusti {len(giusti)}")
        print("  precision: %.2f   recall: %.2f" % (prec, rec))
        for c in fp:
            print("  falso positivo:", candidati[c])
        for c in fn:
            print("  falso negativo:", candidati[c])

# hit rate, accuracy e macro-F1 contro gt/q4.csv
def valuta_q4(file_gt, risposte, nomi_giochi):
    # gt.csv ha colonne qid,labels,label_names,k; labels può avere più codici separati da "|"
    vere = {}
    with open(file_gt, encoding="utf-8") as f:
        for riga in csv.DictReader(f):
            if riga["qid"] in risposte:               # solo i giochi che abbiamo valutato
                vere[riga["qid"]] = {x.rsplit("/", 1)[-1] for x in riga["labels"].split("|")}
    # etichetta del modello -> codice (None se fuori lista o vuota)
    pred = {e: NOME_A_QID.get(normalizza(risposte[e])) for e in vere}
    n = len(vere)
    hit = sum(1 for e in vere if pred[e] in vere[e])
    singole = {e: next(iter(ls)) for e, ls in vere.items() if len(ls) == 1}
    acc = sum(1 for e, l in singole.items() if pred[e] == l)
    f1s = []
    print("\nQ4: etichetta | veri (singoli) | tp | fp | fn | F1")
    for l in sorted(set(singole.values()) | {p for e, p in pred.items() if e in singole and p}):
        tp = sum(1 for e, g in singole.items() if g == l and pred[e] == l)
        fp = sum(1 for e, g in singole.items() if g != l and pred[e] == l)
        fn = sum(1 for e, g in singole.items() if g == l and pred[e] != l)
        f1 = 0.0 if tp == 0 else 2 * tp / (2 * tp + fp + fn)
        f1s.append(f1)
        print(f"  {ETICHETTE_Q4[l]} | {tp + fn} | {tp} | {fp} | {fn} | {f1:.2f}")
    fuori = sum(1 for e in vere if risposte[e] and pred[e] is None)
    vuote = sum(1 for e in vere if not risposte[e])
    print(f"\n  giochi valutati: {n} (con una sola etichetta vera: {len(singole)})")
    print("  hit rate: %.2f" % (hit / n if n else 0.0))
    print("  accuracy: %.2f" % (acc / len(singole) if singole else 0.0))
    print("  macro-F1: %.2f" % (sum(f1s) / len(f1s) if f1s else 0.0))
    print(f"  risposte fuori lista: {fuori} | risposte vuote/rotte: {vuote}")


# Q8: CONTEGGIO PER DECENNIO (nessuna nuova chiamata al modello)

# conta per decennio i giochi che il modello ha accettato in Q1
# run.py la chiama se hai scelto --q8 <file>, usa i predetti di Q1
# Q8 non fa nuove richieste, riusa le decisioni già prese
# una query normale prende l'anno (ex:firstYear) di ogni gioco del set principale
# per quelli che il modello ha accettato calcola il decennio
# esempio: anno 1993 -> 1993 // 10 = 199 (divisione intera) -> 199 * 10 = 1990
# risultato, ad esempio: {1980: 31, 1990: 55, 2000: 48}
def conta_per_decennio(store, predetti):
    conteggi = {}
    q = ("PREFIX ex: <http://example.org/semop/> "
         "SELECT ?e ?y WHERE { ?e ex:inSet ex:set-main ; ex:firstYear ?y }")
    for r in store.query(q):
        if qid(r["e"]) in predetti:
            decennio = (int(r["y"].value) // 10) * 10
            conteggi[decennio] = conteggi.get(decennio, 0) + 1
    return conteggi

# confronta i conteggi per decennio con la soluzione (gt/q8.csv)
# run.py la chiama subito dopo conta_per_decennio
# metrica: errore relativo medio sui decenni in cui i veri positivi sono > 0
# esempio: veri 33, predetti 40 -> errore |40 - 33| / 33 = 0.21
# i decenni con 0 veri positivi non entrano nella media: si stampa solo cosa ha predetto il modello
def valuta_q8(file_gt, conteggi):
    with open(file_gt, encoding="utf-8") as f:
        righe = list(csv.DictReader(f))
    errori = []
    print("\nQ8: decennio | veri | predetti | errore relativo")
    for riga in righe:
        decennio = int(riga["decade"])
        veri = int(riga["positives"])
        pred = conteggi.get(decennio, 0)
        if veri > 0:
            errore = abs(pred - veri) / veri
            errori.append(errore)
            print(f"  {decennio}s | {veri} | {pred} | {errore:.2f}")
        else:
            print(f"  {decennio}s | 0 | {pred} | (non nella media)")
    if errori:
        print("  errore relativo medio: %.2f" % (sum(errori) / len(errori)))