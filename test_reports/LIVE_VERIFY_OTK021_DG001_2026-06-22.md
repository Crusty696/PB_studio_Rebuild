# PB Studio Live-Verify OTK-021 / DG-001 — 2026-06-22

status: FAIL
branch: codex/OTK-021-source-consolidation-2026-06-22
verdict_language: PASS (agent-verify) / FAIL / INCONCLUSIVE

## Auftrag

Autonome Vordergrund-GUI-/GPU-Live-Verifikation nach grüner Nicht-Live-Suite.

## GPU-Recovery

Früherer Blocker wurde im selben Kampagnenlauf erneut geprüft und war behoben:

| Prüfung | Ergebnis |
|---|---|
| GTX 1060 PnP | `OK`, `CM_PROB_NONE` |
| Treiber / VRAM | 546.33 / 6144 MiB |
| PyTorch | `1.12.1+cu113` |
| CUDA | `True`, `device_count=1`, `cuda:0` GTX 1060 |
| H.264-/HEVC-NVENC extern | Exit 0 |
| sichtbarer Systemcheck | CUDA, FFmpeg, ffprobe, Ollama `OK` |

Einzige sichtbare Systemcheck-Warnung: Hugging-Face-Cache nutzt User-Defaultpfad.

## Live-Daten

- Audio: Zyce/Querox MP3, 513.64 s, 44.1 kHz Stereo
- Video: `single_loop_low_profile_proof_60s.mp4`, H.264/AAC, 640×360,
  5 fps, 60 s
- Testprojekt: `Live OTK021 20260622`

## Ergebnisse

| Bereich | Verdikt | Beleg |
|---|---|---|
| Projekt erstellen/öffnen | PASS (agent-verify) | UI-Titel, Projektordner, eigene DB, Projekt-ID 1 |
| Videoimport | PASS (agent-verify) | DB: Video-ID 1, Pfad/Dauer/Codec korrekt |
| Videoanalyse CUDA | PASS (agent-verify) | RAFT/CUDA, SigLIP/CUDA, Captioning, 9/9 DB-Schritte done |
| Waveform-Einzelanalyse | PASS (agent-verify) | 4000 Samples, sichtbare A1-Waveform |
| SCHNITT Waveform | PASS (agent-verify) | sichtbare A1-Wellenform |
| SCHNITT Thumbnails | PASS (agent-verify) | sichtbarer durchgehender V1-Thumbnail-Strip |
| Timeline Lane/Overlap | PASS (agent-verify) | DB: Lane 0, Video 0–60/60–120, Audio 0–513.64 |
| Proxy/NVENC im Importpfad | FAIL | `NVENC_REQUIRED_FAILED` trotz grünem Systemcheck |
| Audio-Komplettanalyse | FAIL | 19/19 CUDA-Chunks, danach Windows-Pfadfehler |
| OTK-021 Stem-Reuse | FAIL | Status done, aber keine lokalen Stem-Pfade/-Dateien |
| Shutdown bei laufenden Tasks | FAIL | Fenster weg, Prozess >60 s headless |
| Auto-Edit/Export | BLOCKED | Beatgrid fehlte; später Task-Mehrfachstarts/Shutdown-Abbruch |

## Bestätigte neue Bugs

- B-562 — Cockpit zeigt `Kein Projekt geladen` trotz erfolgreichem Laden
- B-563 — ProxyCreation-NVENC-Fail trotz grünem Systemcheck
- B-564 — Video-Analysepanel bleibt nach 9/9 bei 1/9
- B-565 — Stem-Gen scheitert nach voller GPU-Berechnung am Windows-Langpfad
- B-566 — OTK-021 Stem-Reuse `done` ohne lokale Artefakte
- B-567 — Audio-Pipeline-Fehler ohne klare UI-Fehlermeldung
- B-568 — Audio-Analysepanel bleibt nach Waveform stale
- B-569 — SCHNITT-Audio-Dropdown zeigt falschen Track
- B-570 — Shutdown mit laufenden Tasks lässt headless Prozess zurück

## Wesentliche Artefakte

- `tests/qa_artifacts/systemcheck_resume_20260622_0956_20260622_095700.png`
- `tests/qa_artifacts/cockpit_project_loaded_20260622_100433.png`
- `tests/qa_artifacts/video_pipeline_60s_20260622_101409.png`
- `tests/qa_artifacts/audio_pipeline_5min_more_20260622_103147.png`
- `tests/qa_artifacts/waveform_single_result_20260622_103616.png`
- `tests/qa_artifacts/schnitt_timeline_initial_20260622_104236.png`
- `logs/pb_studio.log`
- projektspezifische `pb_studio.db`

## Ehrliches Gesamtverdikt

`FAIL`

GPU-/Video-Pipeline und zentrale SCHNITT-Darstellung funktionieren real auf GTX1060.
Release-/Workflow-Freigabe fehlt wegen High-Bugs B-563, B-565, B-566 und B-570.
Kein Bug wurde durch Agent als `fixed` markiert.
