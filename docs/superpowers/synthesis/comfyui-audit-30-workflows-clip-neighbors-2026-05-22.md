---
title: ComfyUI Audit - 30_Workflows/_clip_neighbors.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_clip_neighbors.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_cluster_signatures.json
---

# Audit: `30_Workflows\_clip_neighbors.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_clip_neighbors.json
```

## Nachweisbare Fakten

- Groesse: 330.501 Bytes.
- SHA256: `c3ffd2ffb7f0d74f9e4b72e356ba4cff4c5885dde72e51c41778c0aa2290ea10`.
- JSON Top-Level: `dict`.
- Eintraege: 391.
- Jeder Value ist eine Liste mit exakt 5 Nachbar-Pfaden.
- Nachbar-Referenzen gesamt: 1.955.
- Eindeutige Nachbar-Ziele: 363.
- Unbekannte Nachbar-Referenzen: 0.
- Self-Referenzen: 0.
- Gerichtete Paare: 1.955.
- Davon reziprok gerichtete Paare: 1.050.
- Ziel-Popularitaet: min 1, max 31, avg 5.386.

## PB-Studio-Gegenstueck

- `services\enrichment\compat_graph_builder.py`: baut gerichtete Top-K-Cosine-Nachbarschaften mit `cosine_similarity` und `rank_in_a`.
- `services\graph\graph_service.py`: baut Similarity-Edges aus Embeddings, laesst Self-Edges aus, speichert Edge-Gewicht.
- `services\graph\knn_backend.py`: normalisiert Embeddings und Queries fuer Cosine-KNN; nutzt numpy fuer kleine N und USearch ab 10K, Hard-Cap 50K.
- `brain_service.py`: liest bis zu 5 Nachbarn aus `struct_compat_edge`.
- `tests\enrichment\test_compat_graph_builder.py`, `tests\test_services\test_graph_knn_backend.py`, `tests\test_services\test_graph_service.py`: testen KNN-/Graph-Verhalten.

## Vergleich

Referenz:

- Speichert pro Clip exakt 5 Nachbar-Pfade.
- Enthaelt keine Similarity-Scores, keine Ranks ausser Listenposition, keine Distanzwerte und keine Embedding-Dimension.
- Ist als leichtes Workflow-Handoff fuer Nachbarclips nutzbar.

PB Studio:

- Baut gerichtete Top-K-Nachbarschaften mit Score und Rang.
- Hat Graph-Service und Persistenzpfad ueber `struct_compat_edge`.
- Hat skalierbare Backend-Auswahl fuer KNN.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Referenzdatei ist ein Nachbarschafts-Ergebnis ohne Scores und ohne Generator. PB Studio hat nachweisbar eine reichere Nachbarschaftslogik mit Cosine-Score, Rang und Graph-/Brain-Konsumenten.

## Offen

Wenn spaetere Referenzdateien Generatorcode enthalten, pruefen:

- ob Top-K dort bewusst 5 statt PBs 20 nutzt;
- ob ein exportierbares `clip_path -> top5_neighbors` Handoff-Artefakt fuer Workflow-Tools sinnvoll ist;
- ob die Referenz-Nachbarn aus normalisierten 768-dim Vektoren stammen und wie das zu PBs 1152/768-Konflikt passt.
