# Perf-DB-Cleanup — Code-Abschluss 2026-07-13

Status: `code-complete-live-pending` — kein `fixed` ohne User-Live-Sichtung.

## Task-Belege

| Task | Commit | Ergebnis-/Kostenbeleg |
|---|---|---|
| E1 | `a4cd184` | test33 Dict-SHA identisch; Audio 6→1, Video 4→1 Queries |
| E2 | `f50c402` | Status-Writes identisch; Status-SELECTs 8→1 |
| E3 | `a491f78` | 106 IDs identisch; 1 Query |
| E4 | `6d4ae66` | playback_offset-Endzustand identisch; 0 Video-SELECTs |
| E5 | `68c9781` | Entries/Anchors identisch; 3→2 Queries |
| E6 | `ba33f56` | Repair-Ergebnis identisch; 2 Duration-Queries |
| E7 | `8a37b86` | Entry-Zeiten identisch; 1 Entry-SELECT |
| E8 | `0a32b1f` | 105 Browser-Rows SHA-identisch; 421→3 Queries |
| E9 | `1cc0f0f` | frische Connection/Session; realer Projekt-Swap; 200 Builds 0.449684s→0.004593s |
| E10 | `6cf226e` | 5/5 JPG-SHAs/Reihenfolge/Fehler identisch; 2.1850s→1.6019s |

D-069 FFmpeg-Fix: `90d4fbc`, Merge `71ce7a2`; E10 Merge `1272b6c`.
Kanonisch: FFmpeg/ffprobe v6.1.1 mit Manifest-SHA-Gate, `bin/` bleibt
Git-ignoriert.

## Gesamtregression

- DB-Core isoliert: 221 Testausführungen PASS, 3 skipped.
- D-069/E10 isoliert: 70 PASS; reale H.264→JPG-Parität 5/5; 0.9567s→0.6876s.
- E1-E8 Fokus: 15 PASS; angrenzend 84 PASS.
- Scorer-Mikrobenchmark: ein Hostlast-Ausreißer 34.88ms; danach 6/6
  isolierte Läufe PASS (Median 10.52–14.77ms plus Agentlauf 13.76ms).
- E9: 5 Fokus + 56 DB/Undo + 78/78 Deep-DB PASS.
- DetachedInstanceError-Audit E1-E8 statisch + behavioral: kein Fund.

## Internet-/Primaerquellen-Abgleich

- SQLAlchemy: langlebige Engine pro DB; NullPool oeffnet/schliesst DBAPI-
  Connections pro Nutzung; Query-Loaderoptionen sind kanonischer Weg gegen
  unnoetige Eager-/N+1-Loads.
- SQLAlchemy warnt vor `Engine.dispose()` bei checked-out Connections; E9
  ersetzt beim URL-Swap nur Cache-Referenz.
- Git Worktree `commondir` und PyInstaller `_MEIPASS` bestaetigen D-069-
  Resolver-/Bundle-Design.
- FFmpeg-Doku bestaetigt zeitpunkt-/frame-limit-basierte Bildextraktion;
  Byte-Paritaet wurde zusaetzlich lokal mit exakt gleicher Binary belegt.

## Offen — Live

- E1 sichtbarer Media-Refresh; E3 Brain-Run mit FreezeProbe.
- E4 Auto-Edit; E5 Timeline-Projektload; E7 Anchor-Sync; E8 Storage Browser.
- E9 laufender App-Projektwechsel mit Worker-/Lock-Beobachtung.
- E10 echter langer Videoanalyse-Workflow; CPU-/UI-Beobachtung.
- D-069 voller PyInstaller-Build, installierte App, GUI-E2E.
- User setzt Plan-/Task-`fixed` erst nach Live-Sichtung.
