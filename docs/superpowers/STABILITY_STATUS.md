# PB Studio Stabilitätsstatus — Current

Letztes Update: 2026-07-28 02:47 Europe/Zurich

Gesamtfortschritt: **ca. 12–15 %**  
Risikobasierte Pflichtgates: **2/9 abgeschlossen**
Aktiv: **STAB-1 / B-741 Default-Suite-Ollama-Isolation**

| Phase | Stand | Zustand |
|---|---:|---|
| STAB-0 Governance/Wahrheit | **100 %** | abgeschlossen |
| STAB-1 Testfundament | **ca. 65 %** | B-740 codefix live-pending; B-741 aktiv |
| STAB-2 Acht Live-Workflows | **0 %** | blockiert durch STAB-1 |
| STAB-3 Brain/Lernen A/B | **0 %** | blockiert durch STAB-2 |
| STAB-4 GPU/Threads/Soak | **0 %** | blockiert durch STAB-3 |
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
- B-741 offen: vier weitere Default-Suite-Pfade können echtes Ollama erreichen.
- D-078: breite Suite/Live/GPU/Soak/Release-Tests erst nach übriger
  Fix-/Auditarbeit; je Codefix nur kleinster zwingender Fokus.
- Selbstreview-Restverträge für frühes Skeleton, Source-Status und
  Post-CIM-Exception grün.

## Nächste einzige Task

B-741: vier unmarkierte Default-Suite-Ollama-Pfade hostisolieren.
Keine breite Suite; nur kleinster zwingender Fokuscheck bei Codeänderung.

Diese Datei nach jedem Gate, Blocker, Bugstatus oder Phasenwechsel aktualisieren.
