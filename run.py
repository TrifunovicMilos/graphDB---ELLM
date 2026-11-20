import argparse, os
import semops     
import estrazione  

# argparse legge le parole scritte dopo "python run.py" e le mette in a
p = argparse.ArgumentParser()
p.add_argument("query", help="file della query, es. query/q1.rq")                 # obbligatorio
p.add_argument("--tipo", choices=["filtro", "classifica", "estrai"], default="filtro",
               help="filtro = Q1-Q3, classifica = Q4, estrai = Q5")
p.add_argument("--n", type=int, default=0, help="quanti giochi (0 = tutti)")
p.add_argument("--llm", choices=["finto", "vero"], default="finto")
p.add_argument("--dati", default="data/games/dev", help="cartella dei dati")
p.add_argument("--gt", default=None, help="file della soluzione, es. data/games/dev/gt/q1.csv")
p.add_argument("--q8", default=None, help="file gt/q8.csv: calcola anche il conteggio per decennio (Q8)")
a = p.parse_args()

# freno di sicurezza: col modello vero, molte righe vogliono ore
if a.llm == "vero" and (a.n == 0 or a.n > 100):
    if input("Molte chiamate (circa 15 s l'una senza cache). Continuare? (s/n) ") != "s":
        raise SystemExit("annullato")

# carica il grafo
store = semops.carica_grafo(os.path.join(a.dati, "graph.nt"))
print("triple caricate:", len(store))

if a.tipo == "filtro":
    # candidati = i giochi che arrivano alla FILTER (con la funzione "sempre vero": costo zero)
    candidati = semops.esegui(store, a.query, a.n, semops.funzioni_sempre_vero())
    print("giochi candidati:", len(candidati))

    # la query vera
    llm = semops.llm_finto if a.llm == "finto" else semops.llm_vero
    semops.azzera_stats()
    predetti = semops.esegui(store, a.query, a.n, semops.crea_funzioni(llm))
    print("\ngiochi accettati dal modello:", len(predetti))

    # confronto con la soluzione ufficiale 
    if a.gt:
        semops.valuta(a.gt, candidati, predetti)

    # Q8: conteggio per decennio delle decisioni di Q1 (nessuna nuova chiamata)
    if a.q8:
        if a.n:
            print("ATTENZIONE: Q8 ha senso solo su TUTTI i giochi (--n 0); con --n il confronto è parziale.")
        semops.valuta_q8(a.q8, semops.conta_per_decennio(store, predetti))

elif a.tipo == "classifica":
    # classificazione (Q4): ogni gioco riceve un' etichetta
    candidati = semops.esegui_classifica(store, a.query, a.n, semops.funzioni_classifica_vuote())
    print("giochi da classificare:", len(candidati))

    llm = semops.llm_finto_etichetta if a.llm == "finto" else semops.llm_vero_etichetta
    semops.azzera_stats()
    risposte = semops.esegui_classifica(store, a.query, a.n, semops.crea_funzioni_classifica(llm))

    if a.gt:
        semops.valuta_q4(a.gt, risposte, candidati)

else:
    # estrazione (Q5): ogni gioco riceve un testo libero, poi lo abbiniamo a un'entità
    candidati = estrazione.esegui_valori(store, a.query, a.n, estrazione.funzioni_mappa_vuote())
    print("giochi da elaborare:", len(candidati))

    llm = estrazione.llm_finto_valore if a.llm == "finto" else estrazione.llm_vero_valore
    semops.azzera_stats()
    risposte = estrazione.esegui_valori(store, a.query, a.n, estrazione.crea_funzioni_mappa(llm))

    if a.gt:
        indice, nomi = estrazione.carica_indice(a.dati)     # labels.csv + aliases.csv
        estrazione.valuta_q5(a.gt, risposte, indice, nomi)

s = semops.stats
print(f"\nchiamate vere: {s['chiamate']}, dalla cache: {s['cache']}, tempo LLM: {s['secondi']:.0f}s")
print(f"risposte non valide: {s['non_valide']}, fuori lista: {s['fuori_lista']}")