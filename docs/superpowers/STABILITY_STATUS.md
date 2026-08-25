# PB Studio Stabilitätsstatus — Current

Letztes Update: 2026-08-25 11:13 Europe/Zurich

Gesamtfortschritt: **nicht neu berechnet; letzter belastbarer Wert 27–29 % vom 2026-08-14**
Risikobasierte Pflichtgates: **2/9 abgeschlossen**
Aktiv: **STAB-4 / B-723 GPU-/Cancel-/Projektwechsel-Livepfad**

| Phase | Stand | Zustand |
|---|---:|---|
| STAB-0 Governance/Wahrheit | **100 %** | abgeschlossen |
| STAB-1 Testfundament | **ca. 70 %** | B-740/B-741 codefix live-pending; breite Gates D-078-verschoben |
| STAB-2 Acht Live-Workflows | **100 %** | W1-W8 agent-complete-await-user-marker; Usermarker offen |
| STAB-3 Brain/Lernen A/B | **agent-complete*** | A/B, Feedback, Persistenz und Tool-ChatDock 4/4 live; aktueller Non-Tool-ChatDock userautorisiert uebersprungen/nicht PASS; Usermarker offen |
| STAB-4 GPU/Threads/Soak | **ca. 20 %** | B-723/B-725/B-726 codefix live-pending; Stressgate offen |
| STAB-5 UI-Ehrlichkeit | **0 %** | blockiert durch STAB-4 |
| STAB-6 Installer/Clean-VM | **0 %** | blockiert durch STAB-5 |
| STAB-7 Endabnahme | **0 %** | blockiert durch STAB-6 |

## Aktueller Beweisstand

- STAB-3 Tool-ChatDock mit `qwen2.5:3b`: Learn, Recall, Stats und Explain
  Current-live gruen. B-896 `90e1472`, B-897 `50ce61d`.
- B-738 Non-Tool: User-`fixed`, echter headless Learn-/Recall-Beleg vom
  2026-08-11 und aktueller Regressionstest; kein aktueller ChatDock-PASS.
- STAB-3 bleibt `agent-complete-await-user-marker`; STAB-4/B-723 aktiv.
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
- B-737 code-complete/live-pending: semantischer Timeline-Write,
  Debounce/Lifecycle-Drain, generation-sicheres Shutdown, Fehler-Retry und
  persistiertes Einzelrating nach DB-Neustart. Fokus 27 + 9 + 9 gruen;
  Abschlussreview ohne Critical/High/Medium. App-Livebeweis offen.
- B-757 code-complete/live-pending: Stats-Schema und Stats-UI leiten Grenze
  aus 18 kanonischen Achsen ab; 6 Kernbelege plus verschaerfter Grenztest,
  Ruff/Compileall/Diffcheck gruen; Abschlussreview ohne relevante Findings.
- B-738 code-complete/live-pending: sicherer modellunabhaengiger Gateway mit
  Envelope, reserviertem Learn-Control-Prefix und B-411-Integration; Tool-
  und Phi3/Gemma-Non-Tool-Chat erhalten projektisolierten Recall. Vision nutzt
  read-only Recall-Miss-Fallback plus neueste Cut-Erklaerung. 44 Fokusbelege,
  Learn-Recall-Kreis, Ruff/Compileall/Diffcheck gruen; Abschlussreview ohne
  Critical/High/Medium. ChatDock-/Ollama-/Neustart-Livebeweis offen.
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
- B-740 Current-live: eigener App→Serve→Runner-Prozessbaum; nativer Shutdown
  beendete alle drei PIDs, Port 11434 frei. Usermarker offen.
- W2 Finalmanifest: 15/15 geschützte Pre-Pfade unverändert, 18/18 Quickcheck,
  Host-Settings-SHA unverändert, PB-/Ollama-Prozesse 0. W2 live-pass.

- B-819 gefixt (`532165f`), per Merge `22f96b8` nach `main` integriert;
  4 Fokus-Tests plus Live-Manifest-PASS. Usermarker offen.
- B-758 auf Current HEAD selbst live belegt: CUDA available true,
  GTX 1060 6143 MB, kein FAIL-Modal. Root Cause war extern (HotPlug/TDR).
- W3 Audio V2 komplett live durchlaufen (2026-08-14, drei Runs):
  App-Start, Projekt-Load, Fehlerpfad fehlende Quelldatei, Cancel-Mechanik,
  Cancel-Persistenz nach B-820-Fix, Retry (10 Schritte `done`),
  Neustartvergleich und Stem-Selbstheilung (`htdemucs` auf `cuda:0`,
  VRAM 4.91/3.39 GB, 4 Stems neu). Alle Pre-/Post-Manifeste `pass`,
  fünf Host-/Repo-DBs byte-identisch, Host-Stems unverändert, 0 Prozessreste.
  Usermarker offen.
- B-820 gefixt und live bestätigt (`f46d2eb`): ein User-Cancel überlebt den
  Status-Reconciler. RED 3/4 → GREEN 16, breitere Gegenprobe 125 passed.
- B-822 gefixt und live bestaetigt: Stem-Pfade werden ans aktive Projekt
  gebunden. Mit gezielt auf den Host gesetzten Spalten meldete die App
  `stem_separation` nicht mehr als vorhanden und separierte neu in den
  isolierten Projektordner; Host-Dateien unveraendert.
- B-821 und B-823 gefixt: verworfene Analyse-Klicks landen jetzt per
  `logger.warning` im Logfile; der Pacing-Vocal-Test hat einen festen RNG-Seed.
- B-824 gefixt und live belegt: Stem-Pfade werden projektrelativ gespeichert.
  Alembic `b4c5d6e7f8a9` zieht Bestandsdaten konservativ nach — im Livelauf
  `4 Stem-Pfade projektrelativ gemacht, 4 ausserhalb des Projekts bewusst
  unveraendert gelassen`. Nachzug: elf ungeschuetzte Stem-Leser gefunden und
  nachgezogen, nachdem der erste Livelauf `[StemPlayer] 0 Stems geoeffnet`
  zeigte.
- Neu offen: **B-825** (high) — Alembic-Roundtrip bricht mit
  `no such column: last_used_at` beim `CREATE INDEX idx_model_registry_last_used`.
  Per Baseline-Lauf als vorbestehend belegt, nicht durch B-822/B-824 verursacht.
  Herkunft vermutlich der B-819-Index aus `database/models.py:564`.

## Nächste einzige Task

`LIVE-VERIFY / W4 Videoanalyse inklusive defektem Clip und Reanalyse`.
Alle `open`-Bugs sind abgearbeitet.
Breite/live Tests bleiben gemäß Uservorgabe gebündelt.

Korrektur 2026-08-04: Diese Zeile nannte bis dahin `ROOT-CAUSE / B-738` und
widersprach damit dem Kopf derselben Datei (Z. 7), `ACTIVE_PLAN.md`,
`PLAN_REGISTRY.md` und `AGENT_HANDOFF.md`. B-738 ist seit 2026-08-02
code-complete/live-pending, nicht die nächste Task.

Diese Datei nach jedem Gate, Blocker, Bugstatus oder Phasenwechsel aktualisieren.
