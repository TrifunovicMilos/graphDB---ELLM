"""Semantic operators over a video-game graph (Oxigraph + LLM gateway).

Modules, in the order data flows through them:
  config     fixed settings (group id, gateway address, criteria, label set)
  prompts    tau (entity -> text), instructions, JSON schemas, prompt builders
  gateway    HTTP client of the course LLM gateway (/v1/responses, /v1/embeddings)
  fake       free fake models, for testing the structure without any model
  operators  sem_filter / sem_classify / sem_map / sem_join as Oxigraph functions
  engine     loading the graph, running the .rq queries, sampling
  metrics    evaluation against gt/*.csv (precision, recall, accuracy, ...)
  runfiles   building the official run files (semops-run/1)
  pipelines  one function per query type: ties the modules above together
"""
