# PB Studio Stabilitätsstatus — Current

Letztes Update: 2026-08-02 08:07 Europe/Zurich

Gesamtfortschritt: **ca. 17–20 %**
Risikobasierte Pflichtgates: **2/9 abgeschlossen**
Aktiv: **ROOT-CAUSE / B-740 Current-Live Ollama-Ownership/Cleanup**

| Phase | Stand | Zustand |
|---|---:|---|
| STAB-0 Governance/Wahrheit | **100 %** | abgeschlossen |
| STAB-1 Testfundament | **ca. 70 %** | B-740/B-741 codefix live-pending; breite Gates D-078-verschoben |
| STAB-2 Acht Live-Workflows | **12,5 %** | W1 live-pass; W2 Funktionspfade grün, Prozessgate B-740 rot |
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
- B-278-Fix `1b2f161` integriert; Fokus 3/3. Sichtbarer Retry zeigte
  `Ollama` + `AI ready`; exakter Timeout-Race blieb nicht erzwungen.
- W1-Projektanlage `STAB-W1-A` im isolierten Projektroot gelang.
- B-743 Current-Regression: SettingsStore schrieb dennoch echte
  `%APPDATA%\PBStudio\settings.json` und ergänzte Host-RecentProjects.
  App sofort sauber beendet; Host-Datei nicht geraten zurückgesetzt.
- B-743-Fix `b0aac7e` live: `STAB-W1-B` sichtbar erstellt; Settings und
  RecentProjects nur im Session-APPDATA; Host-JSON + 15 Pre-DBs unverändert;
  neue isolierte Projekt-DB quick_check ok. Kein `fixed` ohne Usermarker.
- B-744 offen: Windows-QSettings-Registrywerte wurden beim isolierten Erststart
  in Session-JSON migriert. Kein Host-Write, aber Host-State-Read.
- B-744-Fix `ebc6546` live: Session-JSON vor Projektanlage `{}`, null
  QSettings-Migration; danach nur isolierter Recent-Project-Pfad. Host-JSON und
  15 geschützte DBs unverändert; neue Projekt-DB quick_check ok.
- W1: drei Projektwechsel, Neustart, Screenshot, Prozesscleanup und
  DB-Vergleich bestanden. B-745 geklärt: vier programmatische
  UI-Automationsschlüsse `spontaneous=False` erzeugten `RPC_E_DISCONNECTED`;
  zwei native `spontaneous=True`-Schlüsse ohne Fatal. Kein Produktdefekt.
- Selbstreview-Restverträge für frühes Skeleton, Source-Status und
  Post-CIM-Exception grün.
- W2 Import/Duplikat/Papierkorb/Bulk-Restore/Reimport/Cross-Project-Reuse
  Current-live bestanden. B-746 nicht reproduzierbar.
- B-747 projektpfadgebundener Reuse-Mute-Key: RED/GREEN, Ruff und sichtbarer
  Current-Live-Dialog grün; Usermarker offen.
- W2 DB-Gate: 15/15 geschützte Pre-Pfade byte-identisch, 18/18 Post-DBs
  `quick_check=ok`, Host-Settings-SHA unverändert.
- W2 Prozessgate rot: `ollama.exe` PID 5944 mit altem W2-App-Parent PID 4620;
  Prozess nicht beendet. W2 bleibt offen.

## Nächste einzige Task

`ROOT-CAUSE / B-740 Current-Live Ollama-Ownership/Cleanup`. Nur betroffenen
Ownership-/Shutdownpfad prüfen; bestandene W2-Funktionspfade nicht wiederholen.

Diese Datei nach jedem Gate, Blocker, Bugstatus oder Phasenwechsel aktualisieren.
