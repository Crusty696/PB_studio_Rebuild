---
title: ComfyUI Audit - 30_Workflows/_clip_clusters.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_clip_clusters.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_clip_embeddings_keys.json
---

# Audit: `30_Workflows\_clip_clusters.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_clip_clusters.json
```

## Nachweisbare Fakten

- Groesse: 55.220 Bytes.
- SHA256: `770c20be412a4e494833a475ad59f411987d8aa0decab7c7dd5182ad154de840`.
- JSON Top-Level: `dict`.
- Eintraege: 391.
- Keys sind absolute Video-Pfade unter `C:/Users/david/Documents/ComfyUI-Studio/00_Assets/01_Videos/...`.
- Values sind alle `int`.
- Cluster-IDs: 20 eindeutige Werte.
- Cluster-ID Minimum: 0.
- Cluster-ID Maximum: 19.
- Singleton-Cluster: 0.
- Groesste Cluster: `15` mit 66 Clips, `2` mit 55 Clips, `19` mit 27 Clips, `7` mit 25 Clips, `12` mit 24 Clips.

## PB-Studio-Gegenstueck

- `services\enrichment\style_bucket_clusterer.py`: UMAP(10d) + HDBSCAN auf SigLIP-Embeddings; liefert Labels, Centroids, Reducer, Probabilities und Degraded-Status.
- `workers\structure_enrichment.py`: schreibt `struct_style_bucket`, `struct_clip_tags`, `struct_compat_edge`; unterstuetzt Fit- und Assign-Modus.
- `database\alembic\versions\2026_04_23_b5d5adc80d3a_add_struct_layer_tables.py`: definiert `struct_style_bucket` und `struct_clip_tags`.
- `services\brain_service.py`, `services\pacing\bridge_mapping.py`, `services\pacing\scorer.py`: konsumieren `style_bucket_id` fuer Brain, Pacing und Scoring.
- `tests\enrichment\test_style_bucket_clusterer.py`, `tests\enrichment\test_umap_hdbscan_pipeline.py`, `tests\enrichment\test_small_library_degraded.py`: testen Clusterer-Verhalten.

## Vergleich

Referenz:

- Speichert eine flache Zuordnung Clip-Pfad -> Cluster-ID.
- Enthaelt keine Embeddings, keine Centroids, keine Confidence/Probability, keine Reducer-Information und keine Lifecycle-Information.
- Ist als leichtes Workflow-Handoff-Artefakt nutzbar.

PB Studio:

- Berechnet Style-Buckets aus Embeddings mit UMAP + HDBSCAN.
- Persistiert Bucket-Centroids und Clip-Tags relational.
- Hat Assign-Modus fuer neue Clips ohne kompletten Refit.
- Nutzt Style-Buckets in Brain/Pacing/Scoring.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Die Referenzdatei ist eine Ergebniszuordnung, kein Clustering-Code. PB Studio besitzt nachweisbar ein umfangreicheres Clustering- und Konsummodell. Ein Import einer flachen Clip-Pfad-zu-Cluster-ID-Datei wuerde PBs bestehende Datenfluesse nicht verbessern, solange der Referenz-Generator und die Embedding-Basis nicht auditiert sind.

## Offen

Wenn spaetere Referenzdateien Generatorcode oder Embedding-Dateien enthalten, pruefen:

- ob die Referenz-Clusterausgabe aus einer deterministischeren Pipeline stammt;
- ob ein optionaler Export `clip_path -> style_bucket_id` fuer Workflow-Handoff nuetzlich ist;
- ob Cluster-IDs stabil ueber Re-Runs gehalten werden.
