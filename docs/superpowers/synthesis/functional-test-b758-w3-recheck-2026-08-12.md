# B-758 isolierter W3-Recheck 2026-08-12

Status: B-758-App-Gate pass; B-819-Follow-up-Manifest pass

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

`W3 Audio V2 komplett, Cancel, Retry, Neustart` im isolierten
Stabilitaetsprojekt fortsetzen.

## B-819 Follow-up

Commit `532165f` verhindert semantisch duplizierte Legacy-Indizes und fuehrt
sieben beabsichtigte Indizes kanonisch in ORM-Metadata. Verifikation:

- 4 Fokus-Tests, PyCompile und Ruff gruen;
- echter zweiter `init_db()`-Lauf schema- und zeilenstabil;
- sichtbarer App-Run `20260812T1354-b819-live-manifest`: Manifest `pass`, Gate
  `passed: true`, Screenshot, GTX-1060-CUDA-Marker und Shutdown gruen;
- geschuetzte Bootstrap-DB vor/nach byte-, schema- und logisch identisch.

Evidence:
`C:/Users/David_Lochmann/AppData/Local/PBStudioB819LiveIsolated/PBStudioStability/20260812T1354-b819-live-manifest/`

B-819-`fixed`-Marker bleibt Userfreigabe.
