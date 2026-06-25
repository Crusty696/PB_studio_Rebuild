# Glossar

> Plan: `LLM-BACKEND-PLATFORM-2026-05-19`
> Status: living document

| Begriff | Bedeutung |
|---|---|
| **Backend** | Konkretes LLM-Daemon-System. Hier: `ollama_embedded` (Default), `lmstudio_external` (Stub). |
| **Provider** | Synonym fuer Backend (in Code-Klassen-Namen). |
| **Rolle** | Aufgabe fuer die ein Modell verwendet wird: `reasoner`, `vision`, `omni`, `embeddings`, `reasoning_heavy`. |
| **Slot** | Aktives Modell pro Rolle. Slot kann zur Laufzeit gewechselt werden (Hot-Reload). |
| **Modell-Pin** | Pro Projekt fixiertes Modell pro Rolle. Verhindert gemischte Provenance. |
| **Selector** | Auto-Auswahl-Logik die best-fitting-within-VRAM-budget waehlt. |
| **VRAM-Budget** | Live verfuegbarer VRAM (pynvml). Reduziert sich wenn Audio-V2 / Brain V3 GPU nutzt. |
| **Registry** | `config/llm_models.json` — Modell-Metadaten, Quality/Speed/VRAM/Lizenz. |
| **Modelfile** | Ollama-spezifische Modell-Konfig: FROM, SYSTEM, PARAMETER, TEMPLATE. |
| **GGUF** | Quantisierungs-Format (llama.cpp-Familie). Default Q4_K_M. |
| **Health-Gate** | Vor jedem Call: Daemon-Ready-Probe. |
| **Streaming** | Server-Sent Events Antwort-Stream. |
| **Tool-Call** | LLM ruft App-Funktion auf, App liefert Result zurueck. |
| **JSON-Mode** | Strukturierter Output mit Schema. |
| **Re-Run-Policy** | Modell wechseln = kein Re-Run. Version-Bump des **gleichen** Modells = manueller Re-Run-Button. |
| **First-Run** | Erster App-Start nach Install ohne Modelle. Wizard fuer Modell-Wahl. |
| **Air-Gap** | (Nicht in diesem Plan. Spaeter.) |
| **GPU_EXECUTION_LOCK** | Existiert in Audio-V2. Wir respektieren via read-only pynvml-Probe. |
| **`status: fixed`** | Setzt nur User nach Live-Verify. |
