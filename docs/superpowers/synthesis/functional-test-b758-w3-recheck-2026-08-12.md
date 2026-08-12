# B-758 isolierter W3-Recheck 2026-08-12

Status: B-758-App-Gate pass; Gesamtmanifest fail durch B-819

## Scope

HEAD `6b2ce85`, Branch `codex/B-758-w3-recheck`, sauberer Worktree,
isolierte APPDATA/LOCALAPPDATA, isolierte Bootstrap-DB, exakter
`--stability-project`-Scope.

## Ergebnis

- Preflight: Treiber 546.33, PnP ok, Torch 1.12.1+cu113/CUDA 11.3,
  genau eine GTX 1060, echter NVENC-Frame gruen.
- App-Gate-JSON `passed: true`.
- Logmarker: CUDA available true, GTX 1060 6143 MB, ModelManager cuda,
  Startup checks komplett.
- Kein CUDA-/NVENC-FAIL, Screenshot erstellt.
- Shutdown graceful; keine PB-/Ollama-Prozessreste.
- Git vor/nach clean, HEAD identisch.

## Gate-Blocker B-819

Manifest `fail`: isolierte Bootstrap-DB 425984→512000 B. Tabelleninhalte und
logischer Content-Hash identisch. Schema bekam 20 Indizes, inklusive
`ix_hotcues_audio_track_id` und `ix_timeline_entries_project_id`, obwohl
Alembic `f0a1b2c3d4e5` sie als verwaiste Duplikate entfernt.

Host-DBs blieben unveraendert. W3 stoppt gemaess erster-Fehler-Regel.

## Evidenz

Extern:
`C:/Users/David_Lochmann/AppData/Local/PBStudioB758Isolated/PBStudioStability/20260812T1323-b758-w3-recheck/`

Screenshot persistent extern im Evidence-Ordner:
`b758_w3_isolated_recheck_20260812_132050.png`

## Naechste einzige Task

`ROOT-CAUSE / B-819 Appstart rekreiert von Alembic entfernte SQLite-Indizes`.
