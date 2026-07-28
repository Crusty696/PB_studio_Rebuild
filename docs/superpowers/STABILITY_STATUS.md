# PB Studio Stabilitätsstatus — Current

Letztes Update: 2026-07-28 11:45 Europe/Zurich

Gesamtfortschritt: **ca. 15–18 %**
Risikobasierte Pflichtgates: **2/9 abgeschlossen**
Aktiv: **LIVE-VERIFY / B-278 Ollama-/AI-Startupstatus**

| Phase | Stand | Zustand |
|---|---:|---|
| STAB-0 Governance/Wahrheit | **100 %** | abgeschlossen |
| STAB-1 Testfundament | **ca. 70 %** | B-740/B-741 codefix live-pending; breite Gates D-078-verschoben |
| STAB-2 Acht Live-Workflows | **0 %** | blockiert durch STAB-1 |
| STAB-3 Brain/Lernen A/B | **0 %** | blockiert durch STAB-2 |
| STAB-4 GPU/Threads/Soak | **ca. 20 %** | B-723/B-725/B-726 codefix live-pending; Stressgate offen |
| STAB-5 UI-Ehrlichkeit | **0 %** | blockiert durch STAB-4 |
| STAB-6 Installer/Clean-VM | **0 %** | blockiert durch STAB-5 |
| STAB-7 Endabnahme | **0 %** | blockiert durch STAB-6 |

## Aktueller Beweisstand

- STAB-0 vollständig synchron.
- 13 reale DBs extern gesichert; bisherige Baseline byte-/logisch identisch.
- B-727 Negativkontrollen bestanden; kein `fixed`, Livebeweis offen.
- B-739 Fokus nach Finalreview-Fixes 30/30 grün.
- Finalreview abgeschlossen; keine weitere Reviewrunde.
- B-739 Commit `c068169`; Post-Commit-Runner pass auf HEAD `0968eed`.
- 13/13 existierende DBs byte-/logisch identisch, quick_check ok;
  0 Prozessreste.
- Syntax/Import: 1120 Dateien kompiliert, 10 Kernmodule importiert; pass.
- Current-Ruff: Exit 0; DB-Evidenz unverändert.
- Alembic: ein Head, Fresh-Upgrade bis Head, quick_check ok.
- B-727-Fokusbeleg bleibt gültig; Schutz-/Testpfade unverändert.
- Current-Pytest: 3362 passed, 54 skipped, 3 deselected.
- Runner-Gate fail: neuer orphaned Ollama runner + conhost; DBs unverändert.
- B-740 Root Cause geschlossen: Host-Ollama aus PBWindow-Layouttest;
  Lifecycle-/Owned-Tree-Fix Commit `abedf08`.
- B-740 Fokus 11/11, Syntax/Ruff und Post-Commit-Prozessgate grün;
  Status `code-fix-pending-live-verification`, kein `fixed`.
- B-741: vier Default-Suite-Pfade hostisoliert; Fokus `4 passed in 8.70s`.
  Current-Suite-/GPU-Livebeweis bleibt offen.
- B-723: Stem- und Video-Exception-Cleanup unter Execution-Lease;
  zwei fokussierte Verträge grün. GPU-/Cancel-Livebeweis bleibt offen.
- B-725: CPU-/Copy-Codecs außerhalb GPU-Lease; zwei Fokusverträge grün.
  FFmpeg-/GPU-/Cancel-Livebeweis bleibt offen.
- B-726: öffentlicher RAFT-Direktpfad unter Execution-Lease; Fokus 2/2.
- B-715: SCHNITT-Projektsnapshot vor Workerstart; Fokus 8/8.
- B-735: 18. lernbare `role_match_weight`-Achse; Fokus 59/59.
- B-736: synthetischen Rankingpfad entfernt; RED→GREEN Fokus.
- B-737 vor Codeedit sauber gestoppt; bleibt offen.
- B-742: Clicklog-Launcher reicht App-Exitcode jetzt durch; Livebeweis offen.
- D-085: User beobachtet jetzt echte Live-Workflows. D-078 bleibt für
  redundante breite Pytest-Suites bestehen.
- W1 Retry 1: Boot/Setup/Hauptfenster/Shutdown Exit 0; reale 13/13 DB-Quellen
  danach byte-/logisch unverändert.
- W1 Retry 2: `KI: Fallback` und `AI ready` gleichzeitig sichtbar, obwohl
  Ollama bereit war. B-278 `partial-fix`; W1 vor Projektanlage gestoppt.
- Selbstreview-Restverträge für frühes Skeleton, Source-Status und
  Post-CIM-Exception grün.

## Nächste einzige Task

B-278 Root Cause des widersprüchlichen Startupstatus beheben; nur
fokussierter Regressionstest, danach beobachteter W1-Live-Retry.

Diese Datei nach jedem Gate, Blocker, Bugstatus oder Phasenwechsel aktualisieren.
