---
title: ComfyUI Audit - 30_Workflows/LTX-2.3_ICLoRA_Motion_Track_Distilled.json
date: 2026-05-24
plan_id: COMFYUI-REFERENCE-AUDIT-INTEGRATION-2026-05-22
reference_file: 30_Workflows\LTX-2.3_ICLoRA_Motion_Track_Distilled.json
status: audited-no-code-change
next_reference_file: 30_Workflows\Migration_Setup.md
---

# Audit: `30_Workflows\LTX-2.3_ICLoRA_Motion_Track_Distilled.json`

## Datei

```text
C:\Users\David Lochmann\Desktop\ComfyUI-Studio-FULL-backup\30_Workflows\LTX-2.3_ICLoRA_Motion_Track_Distilled.json
```

- Groesse: 60.652 Bytes.
- SHA256: `d3f20fa917d2c2a94cf00c433d8c8bf5e0b05281fb376c15bc6bf0c4ae2e0ade`.
- Inventarposition: `30_Workflows` row 21; naechste row 22 ist `30_Workflows\Migration_Setup.md`.
- JSON parse erfolgreich.
- Top-Level-Keys: `id`, `revision`, `last_node_id`, `last_link_id`, `nodes`, `links`, `floatingLinks`, `groups`, `config`, `extra`, `version`.
- Struktur: 39 Nodes, 61 Links, 7 Groups, 1 Floating-Link, Version `0.4`.

## Belegter Zweck

Die Datei ist ein ComfyUI-GUI-Workflow, kein ComfyUI-API-Template.

Belege:

- Sie enthaelt ein `nodes`-Array mit GUI-Positionen, Groessen und Groups.
- Sie enthaelt keine API-Map mit `class_type` pro Node.
- Groups heissen `Load Models`, `Set prompts -> use API nodes to save on memory`, `Load Image`, `Preprocess`, `Generate`, `Decode`, `Sparse track conditioning`.

Der Workflow erzeugt Video aus Bild/Input ueber LTX 2.3 mit Motion-Track-Control, IC-LoRA, Distilled-LoRA, Audio-/Video-Latent-Pfad und SaveVideo-Ausgaben.

Wichtige Node-Typen:

- `CheckpointLoaderSimple`, `LTXVAudioVAELoader`, `LTXAVTextEncoderLoader`.
- `LTXICLoRALoaderModelOnly`, `LoraLoaderModelOnly`.
- `LoadImage`, `GetImageSize`, `LTXVDrawTracks`, `LTXVSparseTrackEditor`.
- `LTXVImgToVideoConditionOnly`, `LTXAddVideoICLoRAGuide`.
- `RandomNoise`, `KSamplerSelect`, `ManualSigmas`, `SamplerCustomAdvanced`, `CFGGuider`.
- `LTXVConcatAVLatent`, `LTXVSeparateAVLatent`, `LTXVTiledVAEDecode`, `LTXVAudioVAEDecode`.
- `CreateVideo`, `SaveVideo`.

## Datenpunkte und Weiterleitung

Eingaben und statische Parameter:

- Modell: `ltx-2.3-22b-dev.safetensors` in `CheckpointLoaderSimple` und `LTXVAudioVAELoader`.
- Text-Encoder: `comfy_gemma_3_12B_it.safetensors`.
- IC-LoRA: `ltxv/ltx2/ltx-2.3-22b-ic-lora-motion-track-control-ref0.5.safetensors`.
- Distilled-LoRA: `ltxv/ltx2/ltx-2.3-22b-distilled-lora-384-1.1.safetensors`.
- Input-Bild: `motion_track_input.jpg`.
- Negative Prompt: `pc game, console game, video game, cartoon, childish, ugly`.
- Latent-Video: 960x544, 121 Frames.
- FPS-Wert im LTX-Conditioning: 24.
- `CreateVideo`-Widgets: 30 FPS fuer zwei Video-Ausgaben.
- Random Seed: `42`, Modus `fixed`.
- Sampler: `euler_ancestral_cfg_pp`.
- Sigmas: `1.0, 0.99375, 0.9875, 0.98125, 0.975, 0.909375, 0.725, 0.421875, 0.0`.

Motion-Track-Daten:

- `LTXVSparseTrackEditor` enthaelt zwei Track-Listen.
- Erste Track-Liste startet bei ungefaehr `(385,239)` und fuehrt ueber interpolierte Punkte bis ungefaehr `(9,295)`.
- Zweite Track-Liste startet bei ungefaehr `(550,246)` und fuehrt vertikal bis ungefaehr `(530,494)`.
- `LTXVDrawTracks` nutzt 512x512 als Track-Canvas-Parameter.

Weiterleitung:

- Bildinput geht ueber Resize/Track-Draw in Sparse-Track-Conditioning.
- Modell und LoRAs gehen in LTX-Conditioning und Sampling.
- Video- und Audio-Latents werden zusammengefuehrt, gesampelt, wieder getrennt, decodiert und in `CreateVideo`/`SaveVideo` geleitet.
- SaveVideo-Ausgaben heissen `tracks` und `output`.

## PB-Studio-Gegenstuecke

Gefundene Gegenstuecke:

- `ui\controllers\video_analysis.py`: startet PBs Video-Pipeline aus `btn_video_pipeline`, sammelt Clip-IDs, dispatcht `VideoAnalysisPipelineWorker`.
- `services\video_pipeline\stages\keyframe_extract_stage.py`: liest `scenes.json`, extrahiert Start/Mid/End-Keyframes und schreibt `keyframes.json`.
- `services\video_pipeline\stages\raft_motion_stage.py`: erzeugt Motion-Daten mit RAFT und schreibt `motion.json`.
- `services\video_pipeline\stages\vlm_caption_stage.py`: liest `keyframes.json`, ruft `VlmCaptionService.caption_keyframes(...)`, schreibt `captions.json`.
- `services\video_pipeline\stages\vlm_caption_service.py`: ist ohne gesetztes Backend Stub (`[VLM not wired - Plan B Phase 11 pending]`).
- `docs\PB_Studio_Architektur_Bericht_2026-05-23.md`: dokumentiert PBs Videofluss `KeyframeExtractStage -> ProxyGenStage -> SigLipEmbedStage -> RaftMotionStage -> VlmCaptionStage`.

Nicht gefunden:

- Kein produktiver PB-Client fuer ComfyUI `/prompt`.
- Kein produktiver PB-Client fuer ComfyUI `/history`.
- Keine PB-Integration fuer LTX, IC-LoRA oder ComfyUI-GUI-Workflow-Konvertierung.
- Kein belegter Loader fuer die in dieser Datei genannten LTX-/Gemma-/LoRA-Safetensors.

## Vergleich

Referenz:

- Starker Spezialworkflow fuer generative Videoerzeugung mit LTX 2.3.
- Enthaltene Motion-Track-Controls sind konkrete Nutzdaten, nicht nur Doku.
- Workflow koppelt Modell-Load, Prompt-Encoding, Bildinput, Track-Control, Sampling, Decode und SaveVideo in einer Datei.

PB Studio:

- Ist laut aktueller Architektur ein Director's Cockpit fuer Medienanalyse, Schnitt, Brain/Pipeline und Projekt-Workflows.
- Analysiert vorhandene Clips, extrahiert Keyframes, Motion und Captions, schreibt DB-/JSON-Artefakte.
- Hat keinen belegten generativen LTX-Videoerzeugungspfad.
- Hat keinen ComfyUI-Runtime-Adapter.

## Integrationsentscheidung

Keine App-Code-Aenderung.

Grund:

- Die Datei ist ein ComfyUI-GUI-Workflow, kein direkt in PB ausfuehrbarer Codeblock.
- Eine Uebernahme wuerde neue externe Runtime-Abhaengigkeit, Workflow-Konvertierung, ComfyUI-Client, Queue-/Timeout-/Output-Resolver, Secret-Handling und VRAM-Policy erfordern.
- Die genannten Modelle (`ltx-2.3-22b-dev.safetensors`, `comfy_gemma_3_12B_it.safetensors`, IC-LoRA, Distilled-LoRA) sind auf GTX 1060 6 GB nicht als lauffaehig belegt.
- ComfyUI/LTX als optionales Backend waere Architekturentscheidung, nicht Nebenprodukt dieses File-Audits.
- PBs Grundziel darf durch diesen Audit nicht unautorisiert von Analyse/Schnitt zu generativer Videoerzeugung erweitert werden.

## Ersetzter Code

Keiner.

## Neuer Code

Keiner.

## Offene Verbesserungsidee

Falls der User spaeter ComfyUI/LTX als optionales Backend autorisiert, braucht es vor Code:

- Decision fuer externes ComfyUI-Backend und Scope.
- Workflow-Konverter oder API-Workflow-Version dieser GUI-Datei.
- Settings fuer Server-URL, Modellpfade und optionalen API-Key.
- Bounded Queue, Timeout, Cancel, Output-Resolver und Fehlerklassifikation.
- VRAM-/RAM-Live-Probe auf GTX 1060 6 GB.
- Input-Mapping fuer PB-Medien/Keyframes zu `motion_track_input.jpg` und Track-Control-Daten.
- Tests mit Stub-Server plus separater Live-Verifikation.

## Verifikation

- Referenzdatei gelesen und als JSON geparst.
- SHA256 gegen Inventar abgeglichen.
- Node-/Link-/Group-Zaehler extrahiert.
- Modellnamen, Assetnamen, SaveVideo-Ausgaben und zentrale Parameter aus `widgets_values` extrahiert.
- PB-Gegenstuecke per Dateiinspektion und Repo-Suche geprueft.
- Keine App-Tests ausgefuehrt, weil kein App-Code geaendert wurde.
- Keine Live-Ausfuehrung in ComfyUI; echte Ausfuehrbarkeit, Modellverfuegbarkeit, Lizenzlage und VRAM-Laufzeit bleiben offen.

## Naechste Datei

`30_Workflows\Migration_Setup.md`
