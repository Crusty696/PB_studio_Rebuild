---
title: ComfyUI Audit - 30_Workflows/_clip_embeddings.npz
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_clip_embeddings.npz
status: audited-no-code-change
next_reference_file: 30_Workflows\_clip_neighbors.json
---

# Audit: `30_Workflows\_clip_embeddings.npz`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_clip_embeddings.npz
```

## Nachweisbare Fakten

- Groesse: 1.118.091 Bytes.
- SHA256: `9cf224081fd45419f78440b36bf55d559d076e76f74c862fd869c7376e21048e`.
- NPZ Keys: `vectors`.
- `vectors` Shape: `(391, 768)`.
- `vectors` dtype: `float32`.
- Zeilenanzahl passt zu `30_Workflows\_clip_embeddings_keys.json`: 391.
- NaN-Werte: 0.
- Inf-Werte: 0.
- L2-Norm min: 0.9999998807907104.
- L2-Norm max: 1.0000001192092896.
- L2-Norm mean: 1.0.
- L2-Norm std: 4.0216264096670784e-08.
- Null-Vektoren: 0.
- Wert min: -0.6554215550422668.
- Wert max: 0.22795623540878296.
- Wert mean: -0.002501771552488208.
- Wert std: 0.03599756211042404.

## PB-Studio-Gegenstueck

- `services\brain_v3\storage\embedding_repository.py`: `SIGLIP_DIM = 768`; `add_video_embedding` validiert Shape `(768,)`.
- `services\video_pipeline\stages\siglip_embed_service.py`: Default-Modell `google/siglip-so400m-patch14-384`; Kommentar sagt 1152-dim; Ausgabe wird per Default `float16`.
- `services\video_pipeline\stages\siglip_embed_stage.py`: schreibt `embeddings.npy` und meldet `embedding_dim`, `dtype`, `model_id`.
- `services\vector_db_service.py`: alter VectorDB-Service setzt `EMBEDDING_DIM = 1152` und normalisiert erst bei Suche.
- `services\video_analysis_service.py`: alter Pfad dokumentiert/gibt 1152-dim SigLIP-Embeddings an.

## Vergleich

Referenz:

- Speichert 768-dimensionale, L2-normalisierte `float32`-Vektoren in einer kompakten NPZ-Matrix.
- Hat separate Pfad-Key-Datei fuer Zeilenordnung.
- Enthaelt keine Modell-ID, keine Clip-ID, keine Scene-ID, keine Hashes und keinen Generator.

PB Studio:

- Hat zwei belegte Dimension-Kontrakte: alter VectorDB-/Videoanalyse-Pfad 1152-dim, Brain V3 768-dim.
- Hat DB-/Unit-bezogene Embedding-Speicherung statt nur positionsbasierter Matrix.
- Normalisiert im alten VectorDB-Suchpfad bei Query und Matrix; Brain-V3-Repository speichert Blob ohne sichtbare Normierung in der gelesenen Datei.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Die Referenzdatei beweist eine saubere 768-dim, L2-normalisierte Matrix, aber sie enthaelt keinen Generator und keine Modellangabe. Der sichtbare PB-Konflikt 1152 vs. 768 ist real dokumentiert, aber eine Umstellung waere Architekturarbeit ueber mehrere Stacks. Aus dieser NPZ-Datei allein ist nicht belegbar, welcher PB-Pfad geaendert werden muss.

## Offen

Separat klaeren, sobald Generator/Modell-Dateien auditiert sind:

- Welches SigLIP-Modell erzeugt die Referenz-Vektoren?
- Soll PB einheitlich 768-dim oder 1152-dim verwenden?
- Soll Embedding-Normierung beim Speichern garantiert werden statt nur bei Suche?
- Braucht PB einen NPZ+Keys Export fuer Workflow-Handoff?
