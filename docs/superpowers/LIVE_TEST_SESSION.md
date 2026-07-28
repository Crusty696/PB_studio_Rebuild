# PB Studio — beobachtete Stabilitäts-Live-Session

Stand: 2026-07-28
Entscheidung: Vault D-085
Arbeitsbranch: `codex/B-727-stability-gate`

## Zweck

Current HEAD als echte App bedienen. User schaut zu. Jede Aussage wird an
Commit, Log, Screenshot und isolierten Projektzustand gebunden.

## Schutzgrenzen

- Nur GTX 1060 über `cuda:0`; kein anderer GPU-Backend.
- Testprojekt ausschließlich unter
  `%LOCALAPPDATA%\PBStudioStability\<run_id>\project`.
- Keine Originalprojekt-/Original-DB-Schreibzugriffe.
- Kein Release, Installer oder `fixed`-Marker ohne spätere Freigabe.
- Erster reproduzierbare Fehler stoppt aktuellen Workflow. Genau ein Bug,
  eine Root Cause, ein Fix.

## Start

Aus kanonischem Current-Worktree:

```bat
start_pb_studio_clicklog.bat
```

Launcher protokolliert Branch, Commit, Python, Clicklog, App-Log, Datenfluss
und GPU-/Prozessressourcen. Exitcode der App wird durchgereicht.

## Workflow-Reihenfolge

1. W1 Boot, neues isoliertes Projekt, Projektwechsel, Shutdown, Neustart.
2. W2 Audio-/Videoimport, Papierkorb, Restore, Reimport.
3. W3 Audio V2 komplett, Cancel, Retry, Neustart.
4. W4 Videoanalyse inklusive defektem Clip und Reanalyse.
5. W5 SCHNITT, Timeline, Preview, Move/Trim/Lock/Anchor, Undo/Redo.
6. W6 Auto-Edit/Pacing mit fixierten Eingaben.
7. W7 Export Hard-Cut/xfade, Cancel/Retry, ffprobe.
8. W8 Persistenz und Shutdown mit/ohne laufende Tasks.
9. Brain-Lern-A/B, GPU-/Cancel-/Projektwechsel-Stress und UI-Ehrlichkeit
   folgen nur, wenn vorherige Workflows keinen blockierenden Fehler zeigen.

## Pro Workflow erfassen

- sichtbarer Ausgang + Screenshot;
- relevante Click-/App-Logs;
- DB vor/nach;
- Prozess-/GPU-Auszug;
- `pass|fail|blocked` mit ehrlicher Grenze.

## Aktueller Halt

B-737 und B-738 bleiben offen. B-737 wurde vor erstem Codeedit sauber gestoppt.
Fortsetzung erst nach dieser beobachteten Live-Session.
