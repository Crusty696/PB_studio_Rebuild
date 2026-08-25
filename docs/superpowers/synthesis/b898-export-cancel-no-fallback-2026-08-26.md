# B-898 / Export-Cancel ohne Render-Fallback

Datum: 2026-08-26
Status: agent-fixed-await-user

## Root Cause

Der ausgelagerte LUFS-Subprocess-Runner erkannte User-Cancel und beendete
FFmpeg, warf danach aber einen generischen `RuntimeError`. Der B-603-
Batchpfad wertete nur `ExportCancelled` als Cancel; der generische Fehler
startete deshalb hard-cut/concat-Fallback samt Standardisierungs-Precheck.
Zwei LUFS-Checks vor und zwischen den Passes gaben bei Cancel ausserdem nur
`False` zurueck und liessen den Export weiterlaufen.

## Fix

- `services.export.ffmpeg_runner.ExportCancelled` ist gemeinsamer
  Cancel-Typ fuer Runner und Export-Orchestrator.
- `services.export_service` re-exportiert denselben Typ; bestehende API
  bleibt erhalten.
- LUFS-Watchdog sowie beide LUFS-Checks werfen diesen Typ.
- Echte Renderfehler bleiben generische Exceptions und behalten B-603-
  Fallback.

## Fokusverifikation

- RED: zwei LUFS-Precheck-Fails; echter Sleeping-Subprocess-Cancel warf
  falschen `RuntimeError`.
- GREEN: 5 direkte Cancel-/No-Fallback-Vertraege; finaler enger Lauf
  4 passed in 1.20 s.
- PyCompile gruen.
- Ruff: Produktdateien und neuer B-880-Test gruen. Alte Cancel-Testdatei nur
  mit Ignore fuer zwei bereits bestehende E731 an unveraenderten Zeilen.
- `git diff --check` gruen vor Live-Lauf.

## Current-Livebeweis

- Sichtbare App PID 8008 im isolierten Stability-Projekt.
- Finalexport startete echten xfade-Batch: FFmpeg PID 3328, Parent 8008,
  `h264_nvenc -preset p4 -cq 18 -pix_fmt yuv420p`.
- Sichtbarer TASKS-`Abbrechen`-Klick endete 00:03:26.516 lokal.
- TaskEngine und ExportWorker loggten kooperativen User-Cancel bereits in
  derselben Sekunde 00:03:26.
- Kein B-603-, Fallback- oder Standardisierungs-Precheck-Marker nach Cancel.
- FFmpeg 0; konkretes `pb_xfb_1_c0vo_13y.mp4` und neue Projekt-`.mp4`/
  `.part`/`.tmp` 0; App responsiv.
- DB `quick_check=ok`, Counts 1/125/147/3/102/1053.
- Graceful Shutdown: App/Ollama/FFmpeg 0, kein Crash/Traceback.

## Grenze

User-`fixed`-Marker bleibt offen. STAB-4-Gesamtgate bleibt separat rot/offen:
aktives Kalt-VRAM +813 MiB > +512 MiB und B-774-Realbeweis.

## Belege

- `logs/pb_studio.log`
- `tests/test_services/test_ffmpeg_cancel.py`
- `tests/test_services/test_b880_export_cancel_contract.py`
- Vault: `wiki/bugs/B-898-export-cancel-startet-fallback.md`
