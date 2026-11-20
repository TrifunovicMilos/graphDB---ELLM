# Q5: sem_map (estrai un valore dal testo) e abbinamento a un'entità
# importa semops per riusare tau, la cache, i contatori ecc.
# sem_map: per ogni gioco il modello risponde con un testo libero, 
# non con una scelta tra opzioni (sem_classify) né con sì/no (sem_filter)
# quel testo va poi abbinato a un'entità del grafo usando labels.csv (nomi) 
# e aliases.csv (altri nomi) e si misura quanti abbinamenti sono giusti

import csv, os, re
from collections import Counter
import pyoxigraph as ox
import semops

EX = semops.EX

# PROMPT

ISTRUZIONI_MAPPA = ("You extract information from a text. Answer the criterion for the item with a short "
                    "value, using the name exactly as written in the text. If the text does not say, "
                    "use an empty string. Answer only with JSON: {\"value\": \"<string>\"}.")

def costruisci_prompt_mappa(criterio, testo_tau):
    return ISTRUZIONI_MAPPA + "\n\nCriterion: " + criterio + "\n\nItem: " + testo_tau


# MODELLO FINTO E MODELLO VERO
# finto LLM per l'estrazione: cerca "developed by X" nel testo e restituisce X
def llm_finto_valore(prompt):
    semops.stats["chiamate"] += 1
    testo = prompt.split("Item:")[1]
    m = re.search(r"(?:developed|created|made) by ([A-Z0-9][\w&.'\-]*(?: [A-Z0-9][\w&.'\-]*)*)", testo)
    return m.group(1).rstrip(".") if m else ""

# modello vero per l'estrazione: restituisce la stringa del campo "value" (o None se rotta)
def llm_vero_valore(prompt):
    return semops._risposta_con_cache(prompt, "value", str)


# sem_map 
# la chiama Oxigraph per ogni riga quando trova nel .rq
# BIND( ex:sem_map(?label, ?lead, "the company that developed the game") AS ?value )
def crea_funzioni_mappa(llm):
    def sem_map(label, lead, criterio):
        risposta = llm(costruisci_prompt_mappa(criterio.value, semops.tau(label.value, lead.value)))
        if risposta is None:
            risposta = ""
        print(f"  [chiamate {semops.stats['chiamate']}, cache {semops.stats['cache']}] {label.value}: {risposta!r}")
        return ox.Literal(risposta)
    return {ox.NamedNode(EX + "sem_map"): sem_map}

# sem_map che restituisce stringa vuota e non costa nulla (per vedere i candidati)
def funzioni_mappa_vuote():
    def sem_map(label, lead, criterio):
        return ox.Literal("")
    return {ox.NamedNode(EX + "sem_map"): sem_map}

# esegue q5.rq e restituisce {codice_gioco: stringa_del_modello}
def esegui_valori(store, file_query, n, funzioni):
    q = semops._leggi_query(file_query, n)
    risultati = {}
    for r in store.query(q, custom_functions=funzioni):
        valore = r["value"]
        risultati[semops.qid(r["e"])] = valore.value if valore is not None else ""
    return risultati


# abbinamento: da stringa a entità (labels.csv + aliases.csv)

def normalizza_nome(testo):
    return " ".join(testo.lower().split()).rstrip(".")

# legge labels.csv e aliases.csv e costruisce due dizionari
def carica_indice(cartella):
    indice, nomi = {}, {}
    for file, colonna in (("labels.csv", "label"), ("aliases.csv", "alias")):
        with open(os.path.join(cartella, file), encoding="utf-8", newline="") as f:
            for riga in csv.DictReader(f):
                indice.setdefault(normalizza_nome(riga[colonna]), set()).add(riga["qid"])
                if colonna == "label":
                    nomi[riga["qid"]] = riga[colonna]
    return indice, nomi

# prova a trasformare la stringa del modello in un codice entità
# risolvi("Nintendo", indice) -> ("Q8093", "ok")
def risolvi(stringa, indice):
    if not stringa.strip():
        return None, "vuota"
    candidati = indice.get(normalizza_nome(stringa), set())
    if len(candidati) == 1:
        return next(iter(candidati)), "ok"
    return None, ("non trovata" if not candidati else "ambigua")


#  VALUTAZIONE 
def valuta_q5(file_gt, risposte, indice, nomi):
    vere = {}
    with open(file_gt, encoding="utf-8") as f:
        for riga in csv.DictReader(f):
            if riga["qid"] in risposte:
                vere[riga["qid"]] = {x.rsplit("/", 1)[-1] for x in riga["values"].split("|")}
    giusti, motivi = 0, Counter()
    sbagliati, irrisolti = [], []
    for e, vs in vere.items():
        s = risposte[e]
        q, motivo = risolvi(s, indice)
        motivi[motivo] += 1
        if q is None:
            irrisolti.append((e, s, motivo))
        elif q in vs:
            giusti += 1
        else:
            sbagliati.append((e, s, q))
    n = len(vere)
    print(f"\nQ5: giochi valutati: {n} (senza soluzione, non contati: {len(risposte) - n})")
    print("  accuracy: %.2f" % (giusti / n if n else 0.0))
    print("  non risolti: %.2f   (vuota %d, non trovata %d, ambigua %d)" %
          (len(irrisolti) / n if n else 0.0, motivi["vuota"], motivi["non trovata"], motivi["ambigua"]))
    print("\n  esempi di risposte SBAGLIATE (gioco | modello -> entità abbinata | vero):")
    for e, s, q in sbagliati[:8]:
        veri = ", ".join(nomi.get(v, v) for v in vere[e])
        print(f"    {nomi.get(e, e)} | {s!r} -> {nomi.get(q, q)} | {veri}")
    print("\n  esempi di NON RISOLTI (gioco | modello | motivo | vero):")
    for e, s, motivo in irrisolti[:8]:
        veri = ", ".join(nomi.get(v, v) for v in vere[e])
        print(f"    {nomi.get(e, e)} | {s!r} | {motivo} | {veri}")