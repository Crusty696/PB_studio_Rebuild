---
title: PB Studio W8 Persistenz und Shutdown — Current Live
date: 2026-08-24
status: agent-complete-await-user-marker
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
phase: STAB-2/W8
current_commit: 435397d
---

# W8 Persistenz und Shutdown — Current Live

## Ergebnis

Alle vier W8-Shutdownvarianten sind agentseitig live bestanden:

| Variante | Ergebnis | Kernbeleg |
|---|---|---|
| Ohne laufende Task | pass | Normaler Fenster-Close, Prozesse 0, DB quick_check ok |
| Laufende Audio-Task | pass | Stems bei 67 Prozent geschlossen, kooperativer Abbruch, keine Partial-Stems |
| Laufende Video-Task | pass | Pipeline mit 112 Videos geschlossen, B-883/B-884-Follow-ups live gruen |
| Laufende Export-Task | pass | FFmpeg lebte unmittelbar vor Prompt-Yes; kooperativer Exportabbruch und Exitcode 0 |

Status bleibt agent-complete-await-user-marker. Fixed- und W8-Phasenmarker
setzt nur User.

## Running-Export-Beweis

- Isoliertes Projekt und isolierte APPDATA/LOCALAPPDATA.
- App PID 4308; Ziel w8_shutdown_running_export_cancel_final_20260824.mp4.
- UI zeigte 95 Video-Clips, 1 Audio-Track, 96 Timeline-Eintraege, 333.9 s,
  Standard H.264 fast und 57 Prozent Fortschritt.
- TASKS zeigte Exportziel plus Running.
- Direkt vor Prompt-Yes lebte FFmpeg PID 13740 mit Parent 4308 und h264_nvenc.
- WM_CLOSE wurde nicht blockierend per Win32 PostMessage gesendet.
- Prompt Laufende Tasks wurde mit Yes bestaetigt.
- Log: Kooperativer Abbruch task_f8ae79405e53 und
  ExportWorker: Export durch User abgebrochen.
- App Exitcode 0; App, Ollama, FFmpeg und Demucs danach 0.
- Zieloutput fehlt erwartungsgemaess; keine neuen pb_xfb-Temps.
- Kein neuer WER/Application-Error.

## DB-Diff

| Feld | Vorher | Nachher |
|---|---:|---:|
| audio_tracks | 3 | 3 |
| video_clips | 125 | 125 |
| scenes | 147 | 147 |
| timeline_entries | 96 | 96 |
| analysis_status | 1053 | 1053 |
| quick_check | ok | ok |
| DB-SHA256 physisch | 34438E89... | 06DCB5BB... |

Physischer Hash wechselte durch normalen App-WAL/Checkpoint. Post-Logical-
Digest: b46d836943f9efd32e005d26517291d3a99cc9cc8b96ac2a35223e28daf0bbd9.
Unmittelbarer Pre-Logical-Digest fuer finalen Exportlauf fehlt; alte
17:43-Baseline wird nicht als direkter Vergleich verkauft.

## Evidenz

- tests/qa_artifacts/w8_persistence_shutdown_verdict_20260824.json
- tests/qa_artifacts/w8_shutdown_export_task_final_20260824.png
- tests/qa_artifacts/w8_shutdown_export_prompt_final_20260824.png
- tests/qa_artifacts/w8_shutdown_no_task_20260824.png
- tests/qa_artifacts/w8_shutdown_audio_task_20260824.png
- tests/qa_artifacts/w8_shutdown_video_task_20260824.png
- logs/pb_studio.log

## Automationsincident

Ein paralleler Vorlauf PID 5156 startete faelschlich mit Host-APPDATA.
Keine Exportaktion erfolgte; App wurde normal geschlossen, Prozesse danach 0.
Host-settings.json wurde um 21:28:09 neu geschrieben. Unmittelbare Pre-Baseline
fehlt; deshalb kein spekulativer Restore. Der gueltige Final-Lauf verwendete
danach ausschliesslich isolierte Stability-Settings.

## DoD

- [x] No-Task-Shutdown live
- [x] Running-Audio-Shutdown live
- [x] Running-Video-Shutdown live
- [x] Running-Export-Shutdown bei lebendem FFmpeg live
- [x] Screenshot und Logauszug
- [x] JSON-Verdict parsebar
- [x] DB-Kerncounts und quick_check vor/nach
- [x] Prozesse und Partialoutput nach Shutdown sauber
- [ ] User setzt W8-/fixed-Marker
