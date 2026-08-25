# STAB-4 / Kombinationszyklus Audio, Video, Ollama, Preview, Export, Cancel, Projektwechsel, Shutdown

Datum: 2026-08-25
Status: agent-complete; User-`fixed`-Marker offen
Produktcode: unveraendert

## Scope

Kanonische Task:

`STAB-4 / einen gezielten Kombinationszyklus Audio, Video, Ollama, Preview, Export, Cancel, Projektwechsel und Shutdown ausfuehren`.

Isolierter Test-Root:

`C:\Users\David_Lochmann\AppData\Local\PBStudioStability\20260823T0438-w4-video`

## Live-Belege

- Preview: physischer Play-Klick im SCHNITT; Anzeige wechselte sichtbar von
  `00:00 / 00:10` auf `00:10 / 00:10`; Stop reagierte.
- Ollama/Chat: `qwen2.5:3b` antwortete im sichtbaren Chat exakt
  `KOMBIZYKLUS_OK`. GPU-Check meldete 2.390.300.672 Bytes VRAM.
- Audio: echter htdemucs-Lauf auf CUDA erreichte Chunk 1/12; physischer
  TASKS-Cancel fuehrte zu kooperativem Abbruch. Ollama-Serve blieb am Leben,
  Runner wurde entladen.
- Video: realer SigLIP-/RAFT-CUDA-Pfad lief bis Clip 15/111. Projektwechsel
  waehrend laufender Task wurde mit korrektem sichtbarem Modal blockiert.
  Physischer Cancel beendete Pipeline; RAFT/SigLIP wurden entladen,
  GPU-Execution-Lock freigegeben.
- DB nach Video-Cancel: `quick_check: ok`, null laufende/pending
  Analysis-Status, Hauptzaehler unveraendert
  `1/125/147/3/102/1053`.
- Export: zweiter gezielter Versuch startete echten App-Kindprozess
  FFmpeg PID 4500 mit `-c:v h264_nvenc -preset p4`; UI zeigte 63 %.
  Physischer TASKS-Cancel beendete FFmpeg. Weder Endziel noch Teilfile blieb.
- Projektwechsel: enger B-748-Scope blockierte `switch-target` absichtlich.
  Nach kontrolliertem Neustart mit `--stability-root` wechselte App real zu
  `W5-Switch-Target`. UI-Titel, Cockpit, Log und Ziel-DB bestaetigten Wechsel.
- Shutdown: native `Alt+F4`-Schluesse beendeten App, eigenen Ollama-Serve,
  Runner und FFmpeg. Log bestaetigte Queue-/Scheduler-/ModelManager-/CUDA- und
  MemoryUpdater-Cleanup.
- Persistenz: beide isolierten DBs `quick_check: ok`. Host-Settings-SHA256
  blieb exakt
  `1f31383f0aeab93b8eab03578573f108941b98ce7289998d9b268246493b9104`.

## Ehrliche Findings / Grenzen

- **B-898 neu, open:** Expliziter Export-Cancel wurde zuerst als
  xfade-Fehler behandelt; hard-cut/concat-Fallback und Standardisierungs-
  Precheck liefen noch rund 13 Sekunden, bevor ExportWorker endete. Cleanup
  war danach sauber. Kein Nebenbei-Fix in dieser Task.
- Erster Exportversuch wurde vor belegtem FFmpeg-Start abgebrochen und gilt
  nicht als Encode-Beleg. Zweiter Versuch lieferte echten NVENC-Beleg.
- Videoauswahl-Reduktion griff nicht; dadurch starteten 111 Videos. Lauf wurde
  nach realer CUDA-Arbeit kontrolliert abgebrochen.
- Ein UI-Fokusfehler schrieb den Switch-Pfad ungesendet in Codex statt in PB
  Studio. Draft wurde sofort entfernt; App erhielt nichts. Projektwechsel
  wurde danach mit explizitem Fensterfokus real wiederholt.
- Kaltes STAB-4-VRAM-Gesamtgate bleibt rot: +813 MiB statt maximal +512 MiB.
- B-774 realer CUDA-Kontextverlust bleibt offen.
- 30-Minuten-Soak bleibt offen.
- Kein breiter Testlauf: nur reale betroffene Pfade und Endkontrollen.

## Quellen

- App-Log: `logs/pb_studio.log` (lokal, automatisch von App geschrieben)
- Vault-Log: `C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\log.md`
- Bug: `wiki/bugs/B-898-export-cancel-startet-fallback.md`

## Naechste einzige Task

`STAB-4 / 30-Minuten-Soak mit GPU-/RAM-/Thread-/Prozess-/DB-Monitoring ausfuehren`.
