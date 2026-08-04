---
title: Rekonstruktion der undokumentierten App-Session 2026-08-02 21:44 bis 2026-08-03 00:21
date: 2026-08-04
author: claude
status: recon-complete-no-user-marker
plan: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
baseline_commit: e85a2c25790e53bfaf6346000b6529714955e548
bezug: [B-758, B-218, B-053, B-621]
---

# Rekonstruktion — App-Session 2026-08-02 21:44 bis 2026-08-03 00:21

## Anlass

Nach der Uebernahme am 2026-08-04 fiel auf, dass Artefakte im Arbeits-Worktree
neuer sind als der letzte Commit (`e85a2c2`), das letzte Manifest
(`20260802T2134-w3-b758-post`) und der letzte Vault-Eintrag (21:35):

- `tests/qa_artifacts/.app_pid` — 2026-08-02 21:44
- `tests/qa_artifacts/.app_stdout.log` — 2026-08-02 21:45
- `tests/qa_artifacts/.app_stderr.log` — 2026-08-03 00:21
- `tests/qa_artifacts/b758-recheck-systemcheck-pass_20260802_214557.png`
- `logs/pb_studio.log` — 2026-08-03 00:21
- `logs/freeze_stacks.log` — 2026-08-02 21:45

Erste Annahme war, dass 2,5 Stunden Live-Arbeit undokumentiert verloren gehen.
**Diese Annahme ist widerlegt.**

## Vorgehen

`logs/pb_studio.log` (16 060 Zeilen) ab dem ersten Treffer `2026-08-02 21:4x`
geschnitten: 602 Zeilen, Zeile 15 459 bis Dateiende. Ausgewertet nach
Zeitverteilung, Loggerverteilung, Fehlermarkern und Ereignismustern.
Nur Lesezugriff, keine Datei im Repo geaendert.

## Belegter Ablauf

| Zeit | Ereignis (woertlich aus dem Log) |
|---|---|
| 21:44:49 | `Logging initialisiert` in `.worktrees/stab1-b727/logs/pb_studio.log` |
| 21:44:49 | `[FREEZE-PROBE] Heartbeat-Watchdog aktiv` -> Start mit `--freeze-probe` |
| 21:44:50 | `GPU-Info Cache: NVIDIA GeForce GTX 1060 | CUDA 11.3` |
| 21:44:56 | `Alembic-Migrationen abgeschlossen (head)` |
| 21:44:59 | `Settings loaded from …\PBStudioStability\20260802T0905-w3\AppData\Roaming\PBStudio\settings.json` |
| 21:45:03 | `Starte CUDA-Check...` |
| 21:45:04 | `PyTorch CUDA compiled: 11.3, Treiber: 546.33` |
| 21:45:04 | `PyTorch CUDA available check: True` |
| 21:45:04 | `GPU erkannt: NVIDIA GeForce GTX 1060 (6143 MB VRAM)` |
| 21:45:04 | `ModelManager initialisiert auf Device: cuda` |
| 21:45:12 | `Ollama ist bereit nach 7.4s` |
| 21:45:57 | Screenshot `b758-recheck-systemcheck-pass_20260802_214557.png` |
| 21:45 – 00:16 | 168 × `Power-Source-Change` + 167 × `weitere Power-Events im Debounce-Fenster unterdrueckt` (B-218) |
| 00:21:06 | `closeEvent: eingetreten (dirty=False, spontaneous=True)`, Ollama gestoppt, EmbeddingScheduler clean, `CUDA synchronize + empty_cache`, `MemoryUpdater-Flush abgeschlossen (0 Pattern, Versuch 1)` |

## Befund 1 — keine verlorene Arbeit

Es wurde **kein Projekt geoeffnet**, **keine Analyse gestartet**, **kein
Workflow gefahren**. Belege:

- `get_active_project_id(): Kein aktives Projekt in der DB gefunden` mehrfach
  beim Start, danach kein Projektwechsel im Log.
- Loggerverteilung der 602 Zeilen: 348 `__main__` (davon 335 Power-Events),
  169 `services.model_manager` (ausschliesslich B-218-Power-Resume-Meldungen),
  17 `services.perf_watchdog`, Rest Startup/Shutdown.
- 0 Treffer fuer `ERROR`, `CRITICAL`, `Traceback`, `UNHANDLED`.
- `MemoryUpdater-Flush … 0 Pattern` beim Shutdown.

Die App stand 2,5 Stunden im Leerlauf, bis sie sauber geschlossen wurde.
Die Codex-Session war zu diesem Zeitpunkt bereits unterbrochen.

## Befund 2 — B-758-Recheck war gruen, aber ohne Gate-Evidenz

Der Systemcheck lief um 21:45:04 vollstaendig durch: CUDA verfuegbar, GTX 1060
mit 6143 MB erkannt. Der Screenshot 21:45:57 zeigt die App ohne FAIL-Modal mit
Kopfzeile `GPU 0.0/6.0`.

Das stuetzt die bereits im Bugfile belegte Root Cause (externer
Surface-HotPlug-/TDR-Zustand, `DGPUPresent=0` um 21:25, stabil erst 21:33:17).

**Ehrliche Grenze:** Dieser Lauf hat **kein Pre-/Post-Manifest**, kein Clicklog,
keinen DB-Diff und kein JSON-Verdict. Er erfuellt den Evidenzvertrag des
Stabilitaetsprogramms nicht und darf **nicht** als STAB-Gate-Beleg gezaehlt
werden. Der kontrollierte Recheck (Auftrag A5) bleibt offen.

## Befund 3 — NVENC im Log nicht belegt

Der Systemcheck meldete am 2026-08-02 21:29 sowohl `CUDA GPU FAIL` als auch
`NVENC Encode FAIL`. Im Log des 21:44-Laufs findet sich **kein** NVENC-Eintrag —
weder Erfolg noch Fehler. Ob der NVENC-Teilcheck beim gruenen Lauf ueberhaupt
protokolliert wird, ist aus diesem Log nicht ableitbar. Beim A5-Recheck gezielt
pruefen.

## Befund 4 — Power-Event-Sturm

335 der 602 Zeilen sind Power-Source-Change-Ereignisse ueber 2,5 Stunden
(168 verarbeitet, 167 im Debounce unterdrueckt), jeweils mit
`CUDA-Context wird beim naechsten Modell-Load geprobed` (B-218). Das ist
dieselbe Hardware-Instabilitaetsklasse wie die belegte B-758-Ursache.

Bewertung: Beobachtung, kein neuer Bug. Der B-218-Debounce funktioniert
offensichtlich wie vorgesehen. Relevanz fuer B-758: die Surface-Power-/HotPlug-
Lage war auch nach 21:45 nicht ruhig. Vor jedem GPU-abhaengigen Live-Gate
sollte der dGPU-Zustand geprueft und im Manifest festgehalten werden.

## Befund 5 — Ollama war erreichbar

`Ollama ist bereit nach 7.4s` widerlegt fuer diesen Zeitpunkt die Notiz aus dem
B-738-Recon, Ollama sei nicht erreichbar gewesen. Fuer den B-738-Livebeweis ist
das eine gute Ausgangslage, ersetzt ihn aber nicht.

## Nebenbefund — bekannte Altwarnungen beim Start

`ingest_service: kein aktives Projekt — falle auf project_id=1 zurueck … (B-053)`
erschien beim Start ohne offenes Projekt. Bekannter Altbezug, hier nur notiert,
nicht bewertet.

## Konsequenzen

1. Kein Nachtrag von Live-Ergebnissen noetig — es gab keine.
2. B-758 bleibt `open`. Der kontrollierte Recheck mit Manifest (A5) bleibt die
   offene Restarbeit; dieser Befund liefert dafuer zusaetzliche Evidenz.
3. Artefakte `.app_pid`, `.app_stdout.log`, `.app_stderr.log` im Worktree
   stammen aus diesem Leerlauf und sind kein Arbeitsbeleg.
4. Kein `fixed`-Marker gesetzt, kein Produktcode geaendert.
