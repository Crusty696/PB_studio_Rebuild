---
title: ComfyUI Audit - 30_Workflows/Bruecke_ComfyUI_API.md
date: 2026-05-24
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\Brücke_ComfyUI_API.md
status: audited-no-code-change
next_reference_file: 30_Workflows\chapters.json
---

# Audit: `30_Workflows\Brücke_ComfyUI_API.md`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\Brücke_ComfyUI_API.md
```

## Nachweisbare Fakten

- Groesse: 11.822 Bytes.
- SHA256: `e2a5c26a9bb10e6d37de710c6b8c9802044d0b200f142cec9be26c27f713e02c`.
- Markdown mit Frontmatter:
  - `type: reference`
  - `project: ComfyUI-Studio`
  - `created: 2026-05-21`
  - `updated: 2026-05-21`
  - Tags: `comfyui`, `api`, `http`, `bridge`, `workflows`, `json`
- Inhalt beschreibt eine externe HTTP-Bruecke zu einer separaten ComfyUI-Instanz unter `C:\Users\david\Documents\ComfyUI`.
- ComfyUI-Server-Port laut Datei: `8000`.
- Kommunikationsmuster:
  - `POST /prompt` mit `{"prompt": workflow}`
  - Antwort mit `prompt_id`
  - Polling `GET /history/{prompt_id}`
  - Output-Datei aus `ComfyUI/output/` lesen
- Workflow-Formen:
  - `*.json`: UI-Form
  - `*.json.api.json`: API-Form
- API-Workflow-Schema:
  - Node-ID/Name als Key
  - `class_type`
  - `inputs`
  - Node-Referenzen als `[source_node_id, output_index]`
- Pflicht: mindestens ein Output-Node mit `OUTPUT_NODE = True`.
- Florence-2 Beispiel nutzt:
  - `VHS_LoadVideoPath`
  - `DownloadAndLoadFlorence2Model`
  - `Florence2Run`
  - `SaveStringKJ`
- Laufzeit-Overrides laut Datei:
  - `load_video.inputs.video`
  - `load_video.inputs.skip_first_frames`
  - `florence_run.inputs.task`
  - `florence_run.inputs.seed`
  - `save_caption.inputs.filename_prefix`
- Output-Finding: `glob(f"{prefix}*.txt")`, `mtime >= after_ts - 2`, neueste Datei.
- Polling-Intervall: 0.5 Sekunden.
- Genannte Default-Timeouts:
  - Florence-2 Single-Frame: 120 s
  - Florence-2 Multi-Frame-Slot: 180 s
  - WAN-i2v 480p Lightning: 60 s
  - WAN-i2v 480p ohne Lightning: 7200 s
- Manifest-Schema ist laut Datei `TODO — noch nicht final`.
- Bekannte Eigenheiten:
  - `keep_model_loaded` spart Ladezeit, belegt aber VRAM.
  - `do_sample: true` plus expliziter `seed` soll deterministisch sein.
  - PowerShell kann Python-stderr als `NativeCommandError` anzeigen.
  - maximal 5 bis 10 parallele Jobs empfohlen; ab ca. 100 queued Jobs wird ComfyUI laut Datei instabil.

## PB-Studio-Gegenstueck

- `services\video_pipeline\trigger_queue.py`: sequentielle Trigger-Queue mit pending/running/done/failed.
- `services\video_pipeline\status_reporter.py`: Stage-Status, Subscriber, Summary.
- `services\video_pipeline\orchestrator.py`: Stage-Orchestrierung mit CancelToken.
- `services\video_pipeline\stages\vlm_caption_stage.py`: schreibt `captions.json`, nutzt `VlmCaptionService`.
- `services\video_pipeline\stages\vlm_caption_service.py`: hat Stub-Modus und optionales `llm_backend.caption_image()`.
- `services\video_pipeline\primitives\gpu_lock_aware.py`: VRAM-Warten fuer GPU-Arbeit.
- Gelesene Suche fand keinen produktiven `ComfyUI`-Client, keinen `/prompt`-/`/history`-Client und kein `*.api.json`-Workflow-Template-System in PB.

## Vergleich

Referenz:

- Hat klares externes ComfyUI-Brueckenmodell mit HTTP-Queue, Polling, Workflow-Templates und Output-Datei-Konvention.
- Dokumentiert konkrete Runtime-Slots fuer Florence-2.
- Dokumentiert VRAM-/Parallelitaetsrisiken.
- Ist eine Architektur-/Betriebsdoku, kein Python-Code.

PB Studio:

- Hat eigene Pipeline-Queue, Status, CancelToken und VLM-Backend-Abstraktion.
- Hat keinen belegten ComfyUI-Bridge-Client.
- Der vorhandene VLM-Backend-Hook koennte theoretisch einen externen Bild-Caption-Client aufnehmen; das ist aus dieser Datei aber nicht implementiert.

## Integrationsentscheidung

Keine Code-Aenderung.

Grund: Diese Datei beschreibt ein externes ComfyUI-System und dessen Betriebsregeln. Eine Integration in PB Studio waere neue externe Runtime-Abhaengigkeit plus Client-, Settings-, Fehler-, Security- und VRAM-Policy-Arbeit. Das Grundkonzept der App darf nicht unauthorisiert auf einen separaten ComfyUI-Server erweitert werden. Aus dieser Markdown-Datei allein ist kein direkt uebernehmbarer Codeblock vorhanden.

## Belegte Verbesserungs-Ideen, nicht implementiert

- Optionaler Backend-Adapter fuer `VlmCaptionService`, der ComfyUI `/prompt` + `/history` nutzt.
- Manifest fuer Workflow-Templates mit deklarativen Runtime-Slots.
- Bounded Queue: 5 bis 10 parallele Jobs als harte Obergrenze fuer externe ComfyUI-Inferenz.
- Output-Datei-Suche mit Prefix + `after_ts`-Filter gegen alte Resultate.
- VRAM-Cleanup-Policy nach `keep_model_loaded`.

## Offen

Naechste passende Dateien pruefen:

- `30_Workflows\florence2_video_caption.api.json`
- `caption_all_clips.py`
- `caption_multiframe.py`
- `florence_task_runner.py`

Erst dort kann belegt werden, ob ein konkreter ComfyUI-Client oder Parser besser ist als PBs vorhandener VLM-/Pipeline-Hook.
