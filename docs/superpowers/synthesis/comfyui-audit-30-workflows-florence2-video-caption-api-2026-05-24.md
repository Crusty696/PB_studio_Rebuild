---
title: ComfyUI Audit - 30_Workflows/florence2_video_caption.api.json
date: 2026-05-24
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\florence2_video_caption.api.json
status: audited-no-code-change
next_reference_file: 30_Workflows\Frontmatter_Schema.md
---

# Audit: `30_Workflows\florence2_video_caption.api.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\florence2_video_caption.api.json
```

- Groesse: 1.088 Bytes.
- SHA256: `d85d60796cd2a4c7b75d0c8d612b331cd1df67961e2084823e8f5aff8cc46bc0`.
- JSON-Top-Level: Dict.
- Nodes: 4.

## Belegter Workflow

Die Datei ist ein ComfyUI-API-Workflow-Template.

Nodes:

1. `load_video`
   - `class_type`: `VHS_LoadVideoPath`
   - `video`: `X://insert/path/here.mp4`
   - `frame_load_cap`: `1`
   - `skip_first_frames`: `0`
   - `select_every_nth`: `1`

2. `load_florence`
   - `class_type`: `DownloadAndLoadFlorence2Model`
   - `model`: `microsoft/Florence-2-large`
   - `precision`: `fp16`
   - `attention`: `sdpa`

3. `florence_run`
   - `class_type`: `Florence2Run`
   - `image`: `["load_video", 0]`
   - `florence2_model`: `["load_florence", 0]`
   - `task`: `more_detailed_caption`
   - `keep_model_loaded`: `true`
   - `max_new_tokens`: `1024`
   - `num_beams`: `3`
   - `do_sample`: `true`
   - `seed`: `1`

4. `save_caption`
   - `class_type`: `SaveStringKJ`
   - `string`: `["florence_run", 2]`
   - `filename_prefix`: `studio_caption`
   - `output_folder`: `output`
   - `file_extension`: `.txt`

## Datenpunkte und Weiterleitung

- Eingabe: Videodateipfad.
- Verarbeitung: ein geladener Frame wird an Florence-2-large uebergeben.
- Ausgabe: Caption-String aus Output 2 von `Florence2Run`.
- Persistenz: Textdatei ueber `SaveStringKJ`.
- Nicht belegt: HTTP-Client, Job-Polling, Fehlerbehandlung, Timeout, Output-Dateisuche; diese Punkte stehen nur indirekt in `30_Workflows\Brücke_ComfyUI_API.md`.

## PB-Studio-Gegenstuecke

Gefundene Gegenstuecke:

- `services\video_pipeline\stages\vlm_caption_stage.py`: liest `keyframes.json`, filtert Keyframes (`all`, `scene_anchors`, `mid_only`), ruft `VlmCaptionService.caption_keyframes(...)`, schreibt `captions.json`.
- `services\video_pipeline\stages\vlm_caption_service.py`: Stub-Mode ohne Backend oder Durchreichen an `llm_backend.caption_image(...)`.
- `services\video_analysis_service.py`: alter Live-Caption-Pfad via `OllamaService.vision(...)`, Modell-Auswahl/Fallback, JSON-Schema, Plain-Text-Fallback, Circuit-Breaker.
- `database\models.py`: `Scene.ai_caption` als JSON fuer `{description, mood, motion, tags}`.
- Tests: `tests\test_services\test_video_model_services.py` prueft Stub und Backend-Durchreichung; `tests\test_services\test_video_caption_model_selection.py` prueft Ollama-Modell-Fallback.

## Vergleich

Referenz:

- Nutzt Florence-2-large ueber ComfyUI.
- Captiont genau einen Frame pro Video-Aufruf (`frame_load_cap: 1`).
- Speichert Plain-Text in eine `.txt`-Datei.
- Haelt Modell geladen (`keep_model_loaded: true`).
- Nutzt `fp16` und `sdpa`.

PB Studio:

- Neuer Video-Pipeline-Pfad captiont mehrere Keyframes pro Szene, ist aber ohne Backend noch Stub.
- Alter Analysepfad hat Live-Captioning via Ollama, JSON-Schema, Modell-Fallback, Fehler-/Pause-Handling und Circuit-Breaker.
- Persistiert strukturierte Captions in `Scene.ai_caption`, nicht nur Textdateien.

## Integrationsentscheidung

Keine App-Code-Aenderung.

Grund:

- Die Datei ist ein ComfyUI-Workflow, kein direkt in PB verwendbarer Python-Code.
- Integration wuerde einen neuen ComfyUI-HTTP-Client, Settings, Runtime-Verfuegbarkeit, Output-Resolver, Fehlerbehandlung und VRAM-Policy brauchen.
- `microsoft/Florence-2-large` mit `fp16` und `keep_model_loaded: true` ist fuer GTX 1060 6 GB nicht ohne Live-VRAM-Test als sicher belegbar.
- PBs alter Live-Pfad hat bereits robuste Fehlerbehandlung und strukturierte Persistenz; PBs neuer VLM-Pipeline-Hook ist absichtlich backend-abhaengig.
- Ohne explizite Architekturentscheidung waere ComfyUI als Caption-Backend ein neuer externer Runtime-Pfad.

## Ersetzter Code

Keiner.

## Neuer Code

Keiner.

## Offene Entscheidung

Wenn ComfyUI als optionales Caption-Backend gewuenscht ist, braucht das einen separaten Architekturentscheid:

- ComfyUI-Server-URL und Verfuegbarkeitscheck.
- Workflow-Template-Override fuer Videopfad und `skip_first_frames`.
- Output-Resolver fuer `SaveStringKJ`.
- VRAM-Regel fuer `keep_model_loaded`.
- Fallback zu bestehendem Ollama-/Stub-Pfad.

## Verifikation

- Workflow-JSON gelesen und Node-Graph geprueft.
- PB-Gegenstuecke per Dateiinspektion geprueft.
- Keine Tests ausgefuehrt, weil kein App-Code geaendert wurde.

## Naechste Datei

`30_Workflows\Frontmatter_Schema.md`
