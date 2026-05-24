---
title: ComfyUI Audit - 30_Workflows/_clip_embeddings_keys.json
date: 2026-05-22
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\_clip_embeddings_keys.json
status: audited-no-code-change
next_reference_file: 30_Workflows\_clip_embeddings.npz
---

# Audit: `30_Workflows\_clip_embeddings_keys.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\_clip_embeddings_keys.json
```

## Nachweisbare Fakten

- Groesse: 53.829 Bytes.
- SHA256: `ea7bfdb3b6d65278fa89a60506b1507012f68c4e4efc047174fb376c85cdddeb`.
- JSON Top-Level: `list`.
- Eintraege: 391.
- Item-Typen: nur `str`.
- Eindeutige Pfade: 391.
- Duplikate: 0.
- Pfade sind absolute Video-Pfade unter `C:/Users/david/Documents/ComfyUI-Studio/00_Assets/01_Videos/...`.
- Companion-Check mit `30_Workflows\_clip_embeddings.npz`: dort existiert Array `vectors` mit Shape `(391, 768)`, also gleiche Zeilenzahl. Die NPZ-Datei wird separat als naechste Datei auditiert.

## PB-Studio-Gegenstueck

- `database\models.py`: `VideoClip.embeddings_path`, `Scene.embedding_indices`.
- `services\video_pipeline\stages\siglip_embed_stage.py`: schreibt `embeddings.npy`.
- `services\vector_db_service.py`: speichert Clip-Embeddings in SQLite-Tabelle `clip_embeddings`.
- `services\brain_v3\storage\embedding_repository.py`: definiert `SIGLIP_DIM = 768` und speichert Video-Embeddings.
- `services\brain_v3\storage\embedding_cache.py`: persistiert Embeddings plus Cache-Metadaten.

## Vergleich

Referenz:

- Nutzt eine separate Keys-Liste, die positionsgleich zur Vektor-Matrix ist.
- Ist kompakt und leicht als NumPy-Handoff zu lesen.
- Enthaelt keine Clip-IDs, Scene-IDs, Hashes, Modell-ID, Embedding-Version oder Projektbindung.

PB Studio:

- Speichert Embeddings mit Datenbankbezug, Clip-/Scene-Metadaten und Loesch-/Projektlogik.
- Brain V3 nutzt 768-dimensionale Video-Embeddings.
- Bestehender VectorDB-Pfad hat delete/search/get_all_embeddings-Operationen.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Die Datei ist nur eine Indexliste fuer eine Vektor-Matrix. PB Studio hat bereits ID-/DB-basierte Embedding-Verwaltung. Ein positionsbasierter Pfad-Key-Index waere fuer PB nur als Export-/Importartefakt sinnvoll, nicht als nachweisbare Verbesserung der App-Logik.

## Offen

Naechste Datei `30_Workflows\_clip_embeddings.npz` prueft die eigentliche Vektor-Matrix.
