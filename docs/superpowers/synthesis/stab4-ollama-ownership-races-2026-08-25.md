# STAB-4 / Ollama-Prozessbesitz und Shutdown-/Cancel-/Projektwechsel-Races

Datum: 2026-08-25
Status: agent-complete; kein neuer Codefix

## Neuer Current-Livebeweis: externe Ollama-Ownership

- App PID 3392 fand beim Start eine bereits aktive Ollama-API. Der Service
  startete keinen eigenen Prozess; externer Serve PID 1464 hatte Parent 8568,
  nicht App PID 3392.
- Vor Shutdown: Ollama HTTP 200 mit fuenf Modellen; isolierte Projekt-DB
  `quick_check=ok`, Counts Video/Scene/Audio/Timeline = 125/147/3/102.
- Nativer `Alt+F4`, `spontaneous=True`: App endete ohne Dialog oder Hang.
- Externer Ollama PID 1464 blieb mit unveraendertem Parent aktiv; API danach
  HTTP 200. Shutdownlog enthaelt keinen `Stoppe Ollama-Prozess`-Eintrag.
- Scheduler, ModelManager, CUDA und MemoryUpdater bereinigten synchron; App-
  und FFmpeg-Prozesse danach 0. DB-Quickcheck und Counts unveraendert.

## Bereits aktueller Beleg derselben STAB-4-Session

- B-723: echter htdemucs-CUDA-Task, kooperativer Cancel, Projektwechsel
  waehrend Task blockiert und danach wieder frei; App/DB responsiv.
- B-725: echter Copy-FFmpeg parallel zu htdemucs-CUDA, beide Tasks gecancelt,
  kein FFmpeg-Rest.
- B-762/B-883/B-884 enthalten bereits reale Video-Shutdown-, Qt-Lifecycle-,
  Hardexit- und Kindprozess-Cleanup-Belege. D-078 und Uservorgabe verbieten
  redundante breite Wiederholung ohne neuen Fehler.

## Ehrliche Grenzen

- Noch kein einzelner Kombinationszyklus Audio, Video, Ollama, Preview,
  Export, Cancel, Projektwechsel und Shutdown.
- 30-Minuten-Soak offen.
- Kalt-VRAM-Gesamtgate bleibt rot (+813 statt maximal +512 MiB).
- B-774 echter CUDA-Kontextverlust nach Dauerlast bleibt nicht auf Kommando
  reproduziert; Code-/Usermarker ersetzt diesen Realbeweis nicht.
- App ist nach dem Shutdown-Test absichtlich geschlossen. Externer Ollama-
  Serve PID 1464 blieb im unmittelbaren Postcheck aktiv und wurde von der App
  nicht angefasst. Beim spaeteren Recheck um 22:09 war er beendet; Endzeitpunkt
  und Ursache sind unbekannt, kein PB-Studio-Prozess lief mehr.

Naechster Task:
`STAB-4 / einen gezielten Kombinationszyklus Audio, Video, Ollama, Preview, Export, Cancel, Projektwechsel und Shutdown ausfuehren`.
