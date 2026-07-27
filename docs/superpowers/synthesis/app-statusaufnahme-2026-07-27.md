# PB Studio — vollständige App-Statusaufnahme 2026-07-27

Status: Audit abgeschlossen; kein Produktcode geändert; Current HEAD nicht live gestartet  
HEAD: `32088fd5d600c4f00670da4eb871d38fb9fc4291`  
Branch: `main`, sauber vor Audit, 9 Commits vor `origin/main`  
Aktiver Plan: `PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16` / D-071 / D-075

## Ehrlichkeitsrahmen

- Current HEAD wurde nicht als App gestartet.
- Keine Vollsuite, kein neuer GPU-Medienlauf, kein Export, kein Build, kein Installer-Test.
- Aktuelle Aussagen beruhen auf Git, Code, Commit-Belegen, vorhandenen Tests, Logs,
  read-only DB-Abfragen und Hardware-/Prozessstatus.
- Letzter belegter echter App-/Auto-Edit-Workflow stammt vom 2026-07-24 und liegt
  vor einem großen Teil der heutigen 54-Commit-Welle.
- `fixed` bleibt User-/Live-Marker. Neue Änderungen sind überwiegend
  `code-fix-pending-live-verification`.

## Gesamturteil

PB Studio ist funktional breit und technisch weit entwickelt. Import, Audio-/Videoanalyse,
Timeline, Auto-Edit, Pacing, Brain, LLM-Actions und Export existieren als echte Produktpfade.
Historische Live-Belege zeigen reale Medienverarbeitung auf GTX 1060.

Current HEAD ist trotzdem nicht freigabefähig:

1. Seit Funktionsaufnahme `8e3a7eb` wurden 154 Dateien mit +16.880/-627 Zeilen geändert.
2. Fokus-/RED-GREEN-Tests sind breit, Current-HEAD-Vollsuite fehlt.
3. Current-HEAD-App-/Medien-E2E fehlt.
4. Current-HEAD-Build/Installer/Release-Workflow fehlt.
5. Governance und Bugfiles hängen hinter Git: Plan nennt B-727 als nächste Task, obwohl
   B-727 sowie viele B-709…B-738 code-seitig bearbeitet wurden.
6. Reale Projekt-DBs enthalten aktuell `mem_learned_pattern=0`; Lernwirkung im Produkt
   ist damit noch nicht live belegt.

Kurz: Entwicklungsbreite hoch. Code-Verifikation mittel bis hoch. Aktuelle Live-Verifikation
niedrig. Releasefähigkeit Current HEAD nicht belegt.

## Statuslegende

- **LIVE-ALT:** realer Workflow belegt, aber vor Current HEAD.
- **TEST-CURRENT:** Current-Code durch Fokus-/Regressionstests gestützt.
- **CODE-PENDING:** Code vorhanden, Current-Live-Test fehlt.
- **OPEN:** bestätigte Lücke oder fehlender Beweis.
- **FEHLT:** Funktion nicht implementiert.

## Bereichsmatrix

### 1. Governance, Git, Planstand

Status: **OPEN**

- Kanonisches Repo/Remote korrekt: `Crusty696/PB_studio_Rebuild`.
- Keine fremde Agent-Session. Startzustand sauber.
- `main` liegt 9 Commits vor `origin/main`.
- Aktiver Plan gültig, Vault-Mirror und Entscheidungen D-071/D-075 vorhanden.
- Active Plan, Vault-Mirror, Bugfiles und Index sind stale:
  - B-727 bleibt `open`/„nächste Task“, obwohl mehrere Guard-Fixes + Tests vorliegen.
  - B-709…B-727 bleiben größtenteils `open`, obwohl zu vielen IDs Fix-Commits existieren.
  - B-732…B-738 bleiben `open`, obwohl Lernkreis-/Brain-Commits integriert sind.
  - Mindestens drei verschiedene Vault-Dateien verwenden ID `B-738`.
- Folge: Git ist aktueller als Single Source of Truth. Nächste Implementierungstask
  ist governance-seitig nicht zuverlässig aus Plan/Vault ableitbar.

### 2. App-Start, Setup, Systemcheck, Shutdown

Status: **LIVE-ALT + CODE-PENDING**

- Setup-Wizard, GTX-1060-Erkennung und Hauptfenster wurden historisch live belegt.
- FFmpeg/ffprobe 6.1.1 inklusive SHA-Identität aktuell grün.
- Current-Code ergänzt/fixiert:
  - Launcher-Env und Exitcodes,
  - Shutdown-Pfad über `closeEvent`,
  - doppeltes `init_db`,
  - CPU-Fallback-Flag-Leser,
  - Fenstergeometrie/Dock-State.
- Current-App-Start fehlt.
- Aktuell sechs `ollama`-Prozesse sichtbar; PB-Studio-Prozess nicht aktiv.
  Ob diese Prozesszahl beabsichtigt ist, wurde nicht diagnostiziert.

### 3. Projekte, DB, Migrationen, Backup, Storage

Status: **TEST-CURRENT + OPEN**

- Historisch: lineare Alembic-Kette, ein Head, FK/WAL/busy-timeout, WAL-sicherer Backup-Core.
- Aktuelle read-only Checks:
  - Repo-DB `quick_check=ok`.
  - `outputs/test-tabelle/pb_studio.db` `quick_check=ok`.
- Current-Code-Fixes:
  - Engine-Swap bei `create_all`-Fehler verhindert,
  - EngineProxy-Connect-Lock verkürzt,
  - Save-As-Projektpfad korrigiert,
  - Storage-Browser-Root injiziert,
  - Manifest-Lock/Undelete-/Backup-Leichen behandelt,
  - unveränderte Artefakte nicht erneut gehasht.
- B-727: Guard blockiert Collection-, Subprozess-, APP_ROOT- und SQLAlchemy-DBAPI-Pfade;
  Fokusläufe bis 92 Tests, Collect-only 2662 Tests mit stabilem DB-SHA.
- OPEN:
  - Bugfile/Planstatus B-727 nicht reconciliert.
  - Kein Current-Vollsuitenbeweis gegen alle realen DBs.
  - Kein Backup-Restore-Workflow.
  - Projekt umbenennen/löschen fehlt.
  - Repo-Root-DB bleibt Legacy-/Test-/Produktzustand vermischt.

### 4. Medienimport, Bibliothek, Papierkorb

Status: **LIVE-ALT + TEST-CURRENT**

- Importpfade für Audio/Video, Metadaten, Cross-Project-Reuse und Papierkorb vorhanden.
- Current-Code:
  - Bulk-Delete mit M1-Timeline-Backup,
  - Reimport räumt SoftDeleteTimelineBackup,
  - Auto-Edit ohne Checkbox nutzt gesamten Pool statt paginierter 100-Clip-Sicht,
  - Storage-Löschung meldet nicht mehr fälschlich Erfolg.
- Fokus-/UI-Tests vorhanden.
- OPEN:
  - kein Current-Live-Import,
  - Audio-Pool weiterhin nicht sortierbar,
  - Cross-Project-Reuse-Performance bei großen Dateien nur teilweise verbessert.

### 5. Audioanalyse V2, Stems, Beat, Waveform

Status: **LIVE-ALT + TEST-CURRENT + OPEN**

- Historisch real belegt:
  - 5531-s-Audio, 198 Demucs-Chunks, GTX 1060,
  - Beat/Grid/Structure/LUFS/AV-Pacing,
  - weiterer 513-s-Lauf.
- Current-Code:
  - Fallback-Werte als `degraded` statt echte Messwerte,
  - degraded-Status in Service/UI,
  - AV-Pacing-Cancel bis Chunk-Loop,
  - tote Stem-Pfade sichtbar degraded,
  - Checkpoint-Write serialisiert,
  - Analysefortschritt-Basis korrigiert.
- Tests: u.a. 21 Audio-/Fallback-Tests plus aktuelle Stage-Regressionen.
- OPEN:
  - kein Current echter Audio-V2-Lauf,
  - lange Analyse-Caps liefern weiter Teilanalyse,
  - Stem-Reencode-RAM-Risiko,
  - Subprogress nicht für alle schweren Stages,
  - GUI-Cancel/Resume/Fehlerdarstellung nicht Current-live belegt.

### 6. Videoanalyse, Szenen, Motion, SigLIP, VLM, Embeddings

Status: **LIVE-ALT + TEST-CURRENT + OPEN**

- Historisch real belegt: SceneDetect, RAFT CUDA, Keyframes, SigLIP 1152d,
  echte Ollama-Vision-Captions.
- Current-Code:
  - Reanalyse löscht Embeddings nicht mehr ohne Ersatz,
  - 0 Embeddings werden degraded statt done,
  - Batch toleriert einzelne defekte Clips besser,
  - Szenen-/Motion-Actions erhalten Captions,
  - echter Motion-Wert erreicht Role-Classifier,
  - RAFT-Cache wird über ModelManager entladen,
  - Visual-Metriken + Rollen-Prototypen + `struct_clip_tags` ergänzt.
- Tests: Enrichment/Role/Visual/Embedding- und Video-Service-Suiten vorhanden.
- OPEN:
  - kein Current GPU-/VLM-Lauf,
  - Enrichment skaliert weiter library-weit und fit-basiert pro Clip,
  - GPU-Lock-/Cleanup-Klasse B-723/B-725/B-726 nicht abschließend live bewiesen,
  - VLM-Qualität/Timeouts offen.

### 7. SCHNITT, Timeline, Undo, Vorschau

Status: **LIVE-ALT + TEST-CURRENT + OPEN**

- Historisch: 94 Segmente, 337.1 s Timeline, Waveform/Thumbnails, Virtualisierung,
  Workspace-Wechsel und Timeline-Perf live belegt.
- Current-Code:
  - Undo-Stack bei Projektwechsel,
  - Lock-/Anchor-/Overlap-Snapshots,
  - Add/Remove/AutoEdit/Trim-Undo vollständiger,
  - Source-Trim an Mediengrenzen geklemmt,
  - Preview-Stream-Generation gegen Seek-Race,
  - Projekt-Generationsguard für SCHNITT-Worker,
  - Auto-Edit-Pool >100 Clips,
  - Loading-Guard.
- Regression: UI-Läufe bis 670 passed; weitere 137/132 Fokusfälle.
- OPEN:
  - Current-App-Sichtung fehlt,
  - letzte Live-Logs zeigen `QGraphicsScene::removeItem`-Warnungen,
  - B-715 synchrone DB-Queries beim Tabwechsel offen,
  - kein vollständiges Ripple-Modell,
  - Cancel-Teilresultat-Verhalten nicht live belegt.
- FEHLT:
  - Split/Razor,
  - sichtbarer Playhead,
  - Klick-Seek auf Ruler,
  - Timeline-Preview statt Clip-Combo,
  - wirksame In/Out-Marker,
  - echtes Timeline-Paste,
  - Undo für Inspector-Edits.

### 8. Auto-Edit und Pacing

Status: **LIVE-ALT + TEST-CURRENT + OPEN**

- Historisch: Auto-Edit mit 94 Cuts; Brain-Reranker, Caption-Mood, SigLIP und
  CrossModalMatcher liefen.
- Current-Code:
  - `struct_clip_tags` erreicht Scorer,
  - Reranker-Adapter und `brain_weight`-Blend,
  - Pattern-Priors,
  - Visual-, Rollen-, Mood-, Musik- und Motion-Signale variieren pro Kandidat,
  - Stem-Bonus-Leerfall,
  - `sample_size=0`-Muster,
  - Budget-Historie begrenzt.
- Tests beweisen Signalvarianz und RED/GREEN-Verhalten.
- OPEN:
  - kein Current Produkt-Wirkungsbeweis „anderer Input → andere Auswahl“,
  - flache UI-Pacing-Kurve kann Section-/LLM-Pacing weiter neutralisieren;
    dazu keine dokumentierte Current-Live-Auflösung,
  - reale Projekt-DBs enthalten 0 `mem_learned_pattern`,
  - Cold-Start-/no-signal-Semantik nicht vollständig entschieden.

### 9. Brain V3, Feedback, automatisches Lernen

Status: **TEST-CURRENT + OPEN**

- Current-Code:
  - achsenspezifisches Credit-Assignment,
  - `axis_contributions` durch Service/Dialog/Logger,
  - echter CutContext,
  - Run-End-Flush,
  - Pattern-Aggregation,
  - Embedding-Cache-Lookup,
  - echte Kandidaten-/Musik-/Rollenfeatures,
  - Studio-Brain-UI mit Audit/Memory/Stats/Steer/Structure/Graph.
- Fokusbelege: Brain-/Action-/Lernkreis-/Varianztests, u.a. 47/50/82er Läufe.
- OPEN:
  - kein Current Auto-Edit → Feedback → Flush → zweiter Auto-Edit Livebeweis,
  - beide geprüften Projekt-DBs haben `mem_learned_pattern=0`,
  - kein Neustartbeweis für persistierte Lernwirkung,
  - Bugfiles B-732/B-733/B-737 bleiben `open`.

### 10. LLM, Chat, Agenten, Ollama

Status: **TEST-CURRENT + OPEN**

- Current-Code:
  - Brain-Actions `recall/stats/explain_cut/learn_note`,
  - Actions wieder im Systemprompt sichtbar,
  - Brain-Kontext in Chat/ask_ai/Pacing-Pfaden,
  - No-Op-Actions melden nicht mehr falschen Erfolg,
  - Save/Auto-Edit-/Media-Actions auf reale APIs verdrahtet,
  - Action-Registry-Testisolation repariert.
- Tests: Brain-Actions, Prompt-Budget, Context-Wiring, neue Chat-Actions.
- OPEN:
  - kein echter Current LLM-Call,
  - kein Beweis für alle Modellfamilien/Tool- und Non-Tool-Pfade,
  - sechs lokale Ollama-Prozesse,
  - Token-Streaming und Chat-Abbrechen fehlen,
  - Multi-Turn-History-Wirkung nicht Current-live belegt,
  - B-738-Bugfile bleibt `open`.

### 11. UI/UX, Navigation, Statusanzeigen

Status: **LIVE-ALT + TEST-CURRENT + OPEN**

- Breite PyQt6-Oberfläche: Material, Analyse, SCHNITT, Stems, Convert, Deliver,
  Chat, Tasks, Studio Brain, Settings, Setup.
- Current-Code:
  - Shortcut-Hilfe korrigiert,
  - Dock-Toggle-Sync,
  - Fensterzustand,
  - Analysefortschritt,
  - Loading-State,
  - Projekt-/Worker-Generation,
  - Preview-Race.
- UI-Testbestand sehr groß; Current-Fokus bis 670 passed.
- OPEN:
  - kein Current GUI-Lauf,
  - bekannte Tastaturzugang-Lücken,
  - synchrone Main-Thread-Queries,
  - große Hotspots (`timeline.py`, `main.py`) bleiben Änderungsrisiko,
  - historische Qt-Warnungen nicht Current-live gegengeprüft.

### 12. Export, Deliver, FFmpeg/NVENC

Status: **LIVE-ALT + CODE-PENDING + OPEN**

- Historisch: valides xfade-Video, 94 Segmente, 10105 Frames; Exportmechanik,
  Rundungs-/Gap-/Timeout-/Cleanup-Schutz.
- Current-Code:
  - echte Export-Presets,
  - 10-bit→GTX-1060-kompatibler Pfad,
  - Preview-Blob-Load reduziert,
  - Trim-Grenzen korrigiert,
  - Launcher-NVENC-Invarianten.
- FFmpeg/ffprobe 6.1.1 SHA aktuell grün.
- OPEN:
  - kein Current Exportlauf,
  - Mehrspur-Audio fehlt,
  - EDL ohne UI-Caller,
  - Deliver-Cancel nur über Task-Dock,
  - xfade-Fallback-/Batchqualität nicht Current-live geprüft.

### 13. GPU, VRAM, Concurrency, Worker

Status: **TEST-CURRENT + OPEN**

- Hardware aktuell korrekt: GTX 1060, Treiber 546.33, 6144 MiB, 0 % Last.
- Current-Code adressiert RAFT-Release, EngineProxy-In-Flight, Task-ID-/Cancel-Races,
  Checkpoint-Writer, PerfWatchdog-TLS, FORCE_CPU und Preview-Generation.
- OPEN:
  - mehrere unabhängige VRAM-Owner ohne gemeinsames Reservierungsbudget,
  - B-723 GPU-Cleanup-Reihenfolge,
  - B-725 CPU/Copy unter globalem GPU-Lock,
  - B-726 RAFT-Direktpfad,
  - kein Current Parallel-GPU-/Ollama-Stresstest,
  - keine Current Liveprüfung für Hot-Unplug/Resume.

### 14. Tests, CI, Qualität

Status: **BREIT, ABER CURRENT-GATE OFFEN**

- Letzte vollständige Default-Suite auf älterem Stand:
  `3062 passed, 53 skipped, 3 deselected`.
- Dieser Lauf schrieb wegen B-727 in reale DB; deshalb kein sauberer Current-Beweis.
- Seitdem viele Fokusbelege: UI, Brain, Audio, DB, Preview, Launcher, Security,
  Storage, Video.
- B-727-Guard hat SHA-/Collection-/Subprozessbelege.
- Current-Vollsuite fehlt.
- Ruff konnte in dieser Session nicht erneut ausgeführt werden:
  `No module named ruff`. Commit `62108eb` dokumentiert historisch
  `ruff check . -> All checks passed`.
- Workflow-Dateien wurden geändert, aber nicht auf GitHub ausgeführt.
- Testmarker-/Gate-Semantik und tatsächliche GPU/e2e-Selektion brauchen Current-CI-Beweis.

### 15. Packaging, Installer, Release

Status: **NICHT CURRENT-RELEASE-READY**

- Historische Frozen-/Installer-/Clean-VM-/Installed-App-Belege vorhanden.
- Current-Code/Workflows wurden danach stark geändert.
- B-720 passt CI/Release-Workflow code-seitig an Repo-Realität an.
- Kein Current Workflow-Run, Build, Smoke, Installer, Clean-VM oder Hash-Bindung.
- In geprüften Release-Ordnern wurde kein aktuelles berichtbares Setup-Artefakt gefunden.
- `main` ist 9 Commits ungepusht.
- Ergebnis: historische Release-Belege gelten nicht für Current HEAD.

### 16. Sicherheit

Status: **TEILWEISE TEST-CURRENT + OPEN**

- B-718: Beat-This-Checkpoint-Hash-Pin code-seitig.
- B-719: Sigma-Escaping/SRI code-seitig.
- Historischer Bandit-Lauf: keine Medium/High-Funde unter damaliger Konfiguration;
  ausgeschlossene Regeln begrenzen Aussage.
- OPEN:
  - kein Current vollständiger Security-/Dependency-Scan,
  - Dependabot-/Dependency-Audit-Lage nicht belegt,
  - mehrere `generic "cuda"`-Pfade historisch gefunden; Current-Gesamtprüfung fehlt,
  - Release-Signing/SmartScreen-Vertrauen nicht Current.

### 17. Dokumentation, Vault, Backlog

Status: **OPEN**

- Umfangreiche Plans, Synthesis, Bugfiles, Agent-Lessons und Handoffs vorhanden.
- Vault-Zählung näherungsweise:
  - 474 `fixed`,
  - 172 `code-fix-pending-live-verification`,
  - 31 `open`,
  - weitere Sonder-/Altstatus.
- Parser traf viele Altformate; Zahlen sind keine harte kanonische Statistik.
- Bug-ID-Duplikate, stale Bodies und stale Statusmarker reduzieren Verlässlichkeit.
- Git/Plan/Vault müssen vor weiterer Codearbeit reconciliert werden.

## Was aktuell gut belegt ist

- Reale GTX-1060-Audio-/Videoanalyse auf älteren Ständen.
- Reale 94-Cut-Timeline und valider xfade-Export auf älteren Ständen.
- DB-Integrität beider lokaler DBs aktuell `ok`.
- FFmpeg-Identität aktuell grün.
- Große Menge Current Fokus-/RED-GREEN-Tests.
- Viele 26.07-Funde wurden tatsächlich code-seitig adressiert, nicht nur dokumentiert.

## Größte offene Risiken

1. Current HEAD nie als kompletter Produktworkflow gelaufen.
2. Current Vollsuite/CI nicht grün bewiesen.
3. Brain-/Pacing-/Lernwirkung nicht live bewiesen; `mem_learned_pattern=0`.
4. GPU-/Concurrency-Restklasse B-723/B-725/B-726.
5. Pacing-Kurven-/Section-Semantik möglicherweise weiter wirkungslos.
6. Keine Current Releaseartefakte.
7. Governance-/Bugstatus-Drift inklusive ID-Duplikaten.
8. Fehlende Editor-Kernfunktionen begrenzen Produktreife unabhängig von Bugs.

## Empfohlene nächste Reihenfolge

Keine Umsetzung in diesem Audit. Sachlich sichere Reihenfolge:

1. Plan/Vault/Bugfiles gegen Git `32088fd` reconciliieren; genau eine Next-Task setzen.
2. Current-Vollsuite mit vorab gesicherten SHA/Größe/Inhalt aller realen DBs.
3. Current-App-Start + Projekt `test-tabelle`.
4. Medien-E2E: Import → Audio/Videoanalyse → SCHNITT → Export.
5. Wirkungs-E2E: Auto-Edit → Feedback → Flush/Neustart → zweiter Auto-Edit;
   DB-Pattern + geänderte Auswahl beweisen.
6. GPU-/Ollama-Parallelstress.
7. Current Build/Installer/Clean-VM/Installed-App.
8. Danach fehlende Editor-Kernfunktionen separat planen.

## Schluss

PB Studio ist kein Rohprototyp mehr. App besitzt echte, breite Produktionspfade.
Current HEAD ist aber ein großer, testgestützter Integrationsstand ohne abschließenden
Live-/CI-/Release-Beweis. Ehrlicher Status:

**Code weit entwickelt. Viele aktuelle Fixes testgestützt. Gesamtprodukt Current HEAD
nicht verifiziert. Release nicht freigegeben.**
