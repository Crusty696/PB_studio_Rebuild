# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
repo_plan: docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-master-offene-tasks-2026-07-16.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-071-master-offene-tasks-konsolidierung.md
paused_plan_id: PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15
paused_plan_next_task: Readiness-Re-Gate nach B-860; externe Trust-Authority bleibt unprovisioned
paused_plan_resume_commit: d365257
updated: 2026-08-23
worktree: C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild
branch: main

## Why This Plan Is Active

User autorisierte am 2026-08-23 explizit den Abbruch der Audit-Fortsetzung und
die Reaktivierung des Masterplans. Audit-Phase--1 bleibt pausiert, nicht
abgeschlossen oder ersetzt. B-860 ist lokal als `d365257` committed.

## Current Next Task

`LIVE-VERIFY / W7 Export Hard-Cut/xfade, 8-/10-bit, alle Presets,
Cancel/Retry; ffprobe prueft Dauer, Frames, Audio und Seek`.

W6 autonomer Scope ist `agent-complete-non-llm`: Flat/Custom jeweils Brain
AUS/AN bei LLM AUS besitzen Screenshot, Logauszug, DB-Diff und parsebares
JSON-Verdict. LLM-AN bleibt wegen VLM/B-867 eine explizite
User-Modellentscheidung; W6 hat deshalb keinen Gesamtmarker. W7 beginnt mit
festem Projekt-/Timelinezustand und Hard-Cut-Baseline. Erster reproduzierbarer
Fehler stoppt den jeweiligen Lauf und oeffnet genau eine Root-Cause-Task.

## Paused Auditplan Handoff

Auditplan pausiert nach B-860-Commit `d365257`. Readiness-Re-Gate und reale
externe Trust-Authority bleiben offen. Kein Audit-Snapshot und kein
Produktaudit wurden freigegeben oder ausgefuehrt.

## Historical Masterplan Context (paused)

Alle Bugs mit Status `open` sind abgearbeitet. Der Vault fuehrte sechs; nach
Pruefung blieben davon zwei echte Defekte, zwei waren stale, einer war
teilweise gefixt und einer war bereits erledigt. Dabei kamen zwei neue Bugs
zutage, beide ebenfalls gefixt.

- **B-825** (gefixt, `b70e165`): der M-38-`downgrade()` scheiterte am
  B-819-Index auf der gedroppten Spalte. `batch_alter_table` baut die Tabelle
  neu und legt reflektierte Indizes wieder an. Fix nur im Downgrade-Pfad.
- **B-815** (gefixt): der Fix von 2026-08-12 hat aus dem Kantenueberschuss
  einen Kantenverlust gemacht — 30 Kanten fehlten, Grad fiel von 5 auf 1-4.
  Loeschen und Schreiben betreffen jetzt dieselbe Menge.
- **B-618** (`partial-fix`): die Numba-Hypothese bleibt widerlegt, die Ursache
  des Absturzes bleibt offen. Gefunden und gefixt wurde dabei ein echter
  Defekt: `_FIT_SUBPROCESS_TIMEOUT_S` war geloescht worden, der Kind-Prozess-
  Schutz im Frozen-Build damit tot.
- **B-628, B-577, B-569** (`cannot-reproduce`): der beschriebene Code existiert
  nicht mehr. Fuer B-628 wurde der Source-Grep-Test durch einen echten
  Verhaltenstest ersetzt; fuer B-577/B-569 belegt eine RED-Gegenprobe, dass die
  bestehenden Tests den Fix wirklich absichern.
- **B-826** (neu, high, gefixt): der Stem-Audio-Cache ignorierte, welche Datei
  geladen wurde. Nach einer Stem-Neuseparation an denselben Pfad rechnete
  Pacing mit dem alten Signal weiter.
- **B-827** (neu, low, gefixt): eine Jitter-Assertion war zu 3,24 % flaky.

Testlage: **732 passed, 0 failed** ueber Pacing/Stem/Compat/Anchor/Enrichment/
Auto-Edit. Statusmarker bleiben durchweg Userrecht — ich habe keinen auf
`fixed` gesetzt.

Weiterhin unangetastet, weil bewusst zurueckgestellt oder Userentscheidung:
sechs `deferred`-Bugs, dreizehn `fixed-unverified`, acht
`code-fix-pending-live-verification` und B-816 (`agent-fixed-await-user`).

AGY-Rest gemaess D-089 ist mit getrennten Commits und ehrlichen Live-Grenzen
abgeschlossen. B-817 und B-818 wurden als direkte AGY-Regressionen repariert;
`fixed` bleibt Userrecht. B-758-Systemcheck ist im exakten isolierten W3-
Harness gruen. B-819 wurde in Commit `532165f` korrigiert: 4 Fokus-Tests,
Syntax/Ruff, isolierter Zwei-`init_db()`-Lauf und sichtbarer App-Manifestlauf
`20260812T1354-b819-live-manifest` sind gruen; geschuetzte Bootstrap-DB vor/
nach byte-, schema- und logisch identisch. `fixed` bleibt Userrecht. B-758-
Manifest-Recheck damit pass; naechste einzige Task ist W3-Fortsetzung.

W3 wurde am Current HEAD `e85a2c2` vor jeder Projektöffnung gestoppt: modaler
Systemcheck meldete `CUDA GPU FAIL` und `NVENC Encode FAIL`; degradierter Start
wurde nicht gewählt. Screenshot und Pre-/Post-Manifeste vorhanden. Repo-Root-
WAL/SHM-Drift wurde extern gesichert und recoverable bereinigt. W3 bleibt 25 %;
Fortsetzung erst nach B-758 Root Cause, kleinstem Fix und Current-Livebeweis.

B-737 ist code-complete/live-pending: semantischer Timeline-Write vor
Pattern-Notifier, Debounce/Run-/Projekt-/App-End-Drain, generation-sicheres
Warten, Fehler-Retry und ehrliche Gewichte-Lernsession. Fokus 27 + 9 + 9
Tests gruen; Abschlussreview ohne Critical/High/Medium. B-757 leitet Schema-
und UI-Grenze jetzt aus 18 kanonischen Achsen ab; Fokus und Review gruen,
App-Livebeweis offen. B-738 ist code-complete/live-pending: sicherer Tool-/
Non-Tool-Gateway, reservierter Learn-Control-Prefix und read-only Vision-
Recall/Explain sind fokussiert gruen. Damalige Folgetask war W3-Liveverify.

Keine redundante breite Pytest-Suite. Live-Session nutzt isoliertes Projekt,
Click-/App-/DB-/GPU-/Prozessbelege. Erster reproduzierbare Fehler stoppt
aktuellen Workflow und öffnet genau eine Root-Cause-Task. B-743 `b0aac7e` und
B-744 `ebc6546` sind live bewiesen: Session-Settings/RecentProjects isoliert,
null QSettings-Migration, Host-JSON und 15 geschützte DBs unverändert. Beide
bleiben ohne Usermarker `code-fix-pending-live-verification`. W1 ist
Current-live bestanden, Usermarker offen. B-745 war
UI-Automations-Schließartefakt; zwei native Windows-Schlüsse ohne Fatal,
kein Produktcodefix. W2-Preflight fand die festgelegten 20 Clip-Fixtures nicht:
Provenienzpfade zeigen auf ein nicht vorhandenes Altprofil. D-086 akzeptiert
deshalb 20 deterministisch ausgewählte MP4-Proxies plus zwei WAV-Stems als
ausschließlich isolierte Kopien. Quellen bleiben read-only.

Details: `docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md`.

W2 Import, Duplikat, Papierkorb, Bulk-Restore, Reimport und Cross-Project-Reuse
sind Current-live grün. B-747 wurde minimal behoben und live belegt. B-740-
Owned-Tree-Cleanup wurde mit echter App→Serve→Runner-Kette und nativem Shutdown
bewiesen. Finalmanifest: reale DBs/Settings unverändert, PB-/Ollama-Prozesse 0.
W2 live-pass, Usermarker offen. W3-Komplettlauf mit vier Stems ist bereits
Teilevidenz; offen bleiben Cancel, Retry, Neustartvergleich und fehlendes Stem.
B-748 Incident beim W3-Start ist recovered und Current-live geschlossen:
Fail-Closed-Stability-Scope blockierte absichtlichen Host-Projektversuch vor
DB-Zugriff; 6/6 geschuetzte Pre-Pfade blieben unveraendert. Usermarker offen.
W3 wird ausschließlich mit `gui_harness.py start --stability-project ...`
fortgesetzt.
B-752 None-Summary-Crash wurde im echten Resume-Pfad behoben und Current-live
bewiesen. B-751 ist Code+Current-live abgeschlossen: AV-Pacing stoppt bei
Chunk 1, Task bleibt `cancelled`, persistierter Retry-Vertrag ist
`status=error/error_message=cancelled`, kein Worker-ERROR und kein falscher
Batch-Erfolg. 13 Fokustests, Syntax/Ruff, Host-DB-Manifeste und isolierter
Runtime-Quickcheck gruen; Usermarker offen. B-753 Pre-Start-Cancel ist
code-complete: RED→GREEN, 15 fokussierte B-753/B-751/B-724-Tests,
Syntax/Ruff sowie echter QThread-Interleaving-Beweis grün. Terminalsignal und
Threadende binnen 2 s belegt; App-GUI-Liveklick/Usermarker offen. Nächste
Root-Cause-Task ist B-750. B-754 (stale `completed_at` nach Cancel) bleibt
eigener offener Bug.

B-750-Follow-up ist code-complete: Canceltext ehrlich; Audio-Retry-all startet
einen resumierbaren Strict-Sequential-Worker; Onset resettiert/läuft
`stem_gen` zur Artefakt-Selbstheilung; zentraler Dispatcher-Claim schützt
Einzel-V2, Batch-V2, Retry und kollidierende StemSeparation pro Projekt/Track.
Release erfolgt erst im QThread-Cleanup. Review-RED 5/5 plus Cross-Path-RED
3/3; final 27 fokussierte B-750/Dispatcher/B-751/B-222-Tests sowie
Syntax/Ruff grün. App-GUI-/Medien-Livebeweis bleibt gebündelt für W3 offen.
Stand-6-Follow-up schließt Re-Review-Lücken: Full-/Batch-V2-/Stem-Cancel und
`Bereits aktiv` werden ehrlich getrennt; Claim-Release deckt frühe Setup-,
Shutdown-, terminal/no-thread- und Fast-Finish-Pfade ab. Final 65 direkte
Lifecycle-/B-750-Regressionen, Syntax, Ruff und Diff-Check grün;
unabhängiger Abschlussreview PASS ohne Critical/High/Medium. B-750 bleibt
`code-fix-pending-live-verification`, weil App-GUI-/Medienbeweis W3 offen ist.
Nächste einzige Task: B-755.

B-754 ist code-complete: Done→Started→Cancel löscht stale `completed_at` im
zentralen `mark_cancelled()`-Conflict-Update. RED→GREEN; drei direkte
Cancel-/Idempotenzverträge, Syntax, Ruff und Diffcheck grün. App-/DB-Live-Retry
bleibt W3. Parallel-Mapping erfasste B-755 (`running` behält Altzeit) und
B-756 (Video-Cancel via `mark_error("cancelled")`) als getrennte Bugs.

B-755 ist code-complete: `mark_started()` löscht stale `completed_at` beim
Übergang Done→Running. RED→GREEN; drei direkte Transitionstests, Syntax, Ruff
und Diffcheck grün. Live-Sichtung bleibt W3.

B-756 ist code-complete: sieben Video-`should_stop()`-Zweige nutzen den
kanonischen `mark_cancelled()`-Vertrag; echte Exceptions bleiben
`mark_error()`. RED 7/7, zwei direkte Routing/Timestamp-Verträge, Syntax, Ruff
und Diffcheck grün. Video-Live-Cancel bleibt W4. Gemäß Uservorgabe breite/live
Tests erst nach Codeaufgaben.

B-737 ist code-complete: ein semantisches Brain-Timeline-Rating schreibt
`mem_decision.user_rating`, plant Pattern-Aggregation und persistiert nach
DB-Neustart; Feedback unter 20 Events flusht per Debounce/Lifecycle. Shutdown
drainiert Nachfolgegenerationen, Best-Effort kann nicht endlos loopen.
Gewichte-Lernsession ist mangels autoritativer Run-/Scene-Verknuepfung ehrlich
separat. Kein App-Livebeweis, daher `code-fix-pending-live-verification`.
B-757 ist code-complete/live-pending: `BRIDGE_AXIS_COUNT` bindet Stats-Schema,
Label und Progressbar an `BRIDGE_AXES`; sechs Kernbelege plus verschaerfter
18/19-Grenztest, Ruff, Compileall und Diffcheck gruen. Abschlussreview ohne
Critical/High/Medium.

B-738 ist code-complete/live-pending: echter Orchestrator-Tool-/Non-Tool-Pfad
erhaelt projektisolierten Recall. Non-Tool-Aktionen brauchen eindeutigen
`pb_brain_gateway=v1`-Envelope; persistentes Learn zusätzlich reservierten
User-Prefix mit Doppelpunkt. Vision erhaelt Recall-Miss-Fallback und neueste
Cut-Erklaerung read-only, Fachprompt bleibt letzte Anweisung. Fokus 44 Tests,
Learn-Recall-Kreis, Ruff, Compileall und Diffcheck gruen; Abschlussreview ohne
Critical/High/Medium. Kein ChatDock-/Ollama-/Neustart-Livebeweis. Naechste
einzige Task: `LIVE-VERIFY / W3 Audio V2 Cancel, Retry, Neustart und fehlendes
Stem`.

## Agent Behavior

- Jede Task einzeln committen und im Vault loggen (Hauptagent).
- `fixed` setzt nur der User nach Live-Test.
- Nur eine Task aus einem Bucket zur Zeit; Gates respektieren.

## Übergabe an Codex, 2026-08-15

Der Arbeitsstand dieser Sitzung ist vollständig dokumentiert in
`docs/superpowers/HANDOFF-CLAUDE-AN-CODEX-2026-08-15.md`. Dort stehen die
16 Commits mit Messwerten, die geänderte Schnitt-Architektur, die offenen
Entscheidungen des Nutzers und die Fehler der Vorgänger-Sitzung.

Offene Nutzer-Entscheidungen (nicht ohne Antwort umsetzen):
- LLM-Modellwahl je Aufgabe (B-770 erzwingt derzeit ein Vision-Modell auch
  für Text-Pacing, was jeden Auto-Edit 300 s Timeout kostet)
- Multi-Modell-Pacing (Audio-Modell + Vision-Modell im Zusammenspiel)
- B-832 Vibe-Feld: Notnagel oder ins Scoring einweben
- „Timeline generieren": Vorschau belassen oder Schreibpfad geben
