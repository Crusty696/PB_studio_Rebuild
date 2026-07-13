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

## E-Live-GUI-Ergebnis 2026-07-13 (pb-gui-tester, echte App, test33)

- E5 Timeline-Projektload PASS; E8 Storage-Browser PASS (105 Quellen/5.7GB).
- E1/E3/E4/E9 FAIL wegen Main-Thread-Freezes 2-14s (B-620: synchrone
  AnalysisStatus-DB-Queries im Qt-Notify); funktional korrekt (Auto-Edit
  1428 Segmente, Projektwechsel ohne DB-Lock).
- E7 FAIL: Anchor-Sync No-Op (B-619, getrennte Datenquellen Dialog vs.
  `_anchor_map`).
- E10 FAIL KRITISCH: App verschwindet spurlos bei Struktur-Enrichment
  (B-618, Numba-JIT-Kaltstart `umap`/`pynndescent`).
- B-621: Watchdog-Idle-Messartefakte (nur informativ).
- Gesamt: RED — Live-Abnahme des Plans nicht bestanden; Bug-Triage beim User.

## Offen — Live
- D-069 PyInstaller/Frozen-Smoke PASS: 14,839 Dateien, 5,926,420,584 Bytes;
  Bundle-FFmpeg/ffprobe-SHAs exakt Manifest.
- Frozen-GUI-Live 2026-07-13 PASS: `verify_frozen_gui_workflow.py` Exit 0,
  Fenster responsiv, 63 UIA-Labels, alle 4 Workflow-Gruppen, Screenshot
  `frozen_gui_workflow_20260713_072304.png`.
- Installer 2026-07-13 ERZEUGT: NSISBI-Fund (Extra-Ebene `nsis-binary-7069-1`
  im Entpackpfad, daher frueherer stiller Standard-NSIS-Fallback);
  `PB_NSISBI_MAKENSIS`-Override + `PB_SKIP_PYINSTALLER=1` -> Build Exit 0.
  EXE 424,755 B SHA256 `E9FD7313...C9F1FFD7`; NSISBIN 2,817,285,191 B SHA256
  `FF1A80AC...7757F76D`. Release-Gate EXIT=0; Evidence-Matrix
  `release_ready=true`.
- Release-Kette 2026-07-13 (User-Freigabe): Installer signiert (Valid +
  DigiCert-Timestamp; signierte EXE 432,232 B SHA256 `EAC4B9DB...C325DF2F`),
  Silent-Install per-user PASS (Installed-EXE byte-identisch Frozen-EXE,
  HKCU-Key `PBStudio` ok), Installed-App-GUI-Proof PASS mit neuen Hashes
  (Screenshot `installed_app_gui_workflow_20260713_073746.png`).
  main gepusht (`1e31f35`).
- Clean-VM VERTAGT (User): Windows Sandbox host-defekt — 0x800706EF auch
  ohne Config; nach Host-Reboot/CmService-Neustart
  `run_vm001_windows_sandbox.ps1` gegen neue Hashes nachziehen.
- User setzt Plan-/Task-`fixed` erst nach Live-Sichtung.
