# PB Studio Active Plan

status: active
active_plan_id: PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16
repo_plan: docs/superpowers/plans/2026-07-16-master-offene-tasks-konsolidierung.md
vault_mirror: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\synthesis\plan-master-offene-tasks-2026-07-16.md
decision: C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio\wiki\decisions\D-071-master-offene-tasks-konsolidierung.md
paused_plan_id: PB-STUDIO-EXHAUSTIVE-LINE-FEATURE-AUDIT-2026-08-15
paused_plan_next_task: Readiness-Re-Gate nach B-860; externe Trust-Authority bleibt unprovisioned
paused_plan_resume_commit: d365257
updated: 2026-08-27
worktree: C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild
branch: main

## Why This Plan Is Active

User autorisierte am 2026-08-23 explizit den Abbruch der Audit-Fortsetzung und
die Reaktivierung des Masterplans. Audit-Phase--1 bleibt pausiert, nicht
abgeschlossen oder ersetzt. B-860 ist lokal als `d365257` committed.

## Current Next Task

`PACING-PRIORITAET / B-893 echten Auto-Edit-Livepfad fuer angeglichenen WeightStore-Context belegen`.

B-907 ist live-verifiziert abgeschlossen: normaler Worktree-App-Start,
spontaner MainWindow-Close, kompletter Cleanup, kein RuntimeError/Traceback.
Der direkte Shutdown-Blocker ist damit entfernt. B-893-Liveabnahme nutzt
normalen Launcher und Userprojekt `123454321`.

B-893 Root-Cause-Fix ist code-complete: Produkt-Reranker nutzt BPM-Pace und
candidate-spezifische Motion-Quartile wie spaetere Feedback-Rekonstruktion.
Fokustest `1 passed in 0.93s`; echter Auto-Edit-UI-Lauf fehlt. Status
`code-fix-pending-live-verification`; B-895 beginnt erst nach ehrlicher
B-893-Liveabnahme. Evidence:
`docs/superpowers/synthesis/b893-weightstore-context-alignment-2026-08-27.md`.

Userentscheid 2026-08-27: sichtbarer Pacing-/Auto-Edit-Bereich ist wichtigstes
App-Element und hat ab jetzt oberste Produktprioritaet. Reihenfolge innerhalb
aktiven Masterplans: B-893 (high), B-895 (high), B-894 (medium), B-888
(medium), danach B-832 mit expliziter Vibe-Produktentscheidung. Laufende
Control #26 Evidence wird sauber committed; B-906 bleibt als separater
Medium-Fund offen und wartet hinter Pacing.

Control #26 Erfolgspfad ist elementgenau belegt: echter CrashDialog erzeugt
genau einen sichtbaren/aktiven Log-Button; echter QTest-Mausclick reicht
existierende Logdatei an Windows-Viewer weiter. Zieltest `1 passed in 0.84s`,
kein Produktcodeedit. Finding B-906: fehlende Logdatei endet sichtbar still;
OS-Open-Fehler bleiben ungefangen. Status `finding-open:B-906`. Evidence:
`docs/superpowers/synthesis/stab5-control-26-crash-log-open-2026-08-27.md`.

Control #25 ist elementgenau belegt: echter AboutDialog erzeugt genau einen
sichtbaren/aktiven Accent-Button `Schliessen`. Echter QTest-Mausclick emittiert
Accepted genau einmal, setzt Accepted-Resultat und versteckt Dialog. Zieltest
`1 passed in 2.02s`, kein Produktcodeedit. PBWindow-/About-Menu-Livepfad bleibt
offen. Status `target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-25-about-close-2026-08-27.md`.

Control #24 ist elementgenau belegt: echter AboutDialog erzeugt genau einen
sichtbaren/aktiven Dokumentationsbutton. Echte QTest-Mausclicks erreichen lokale
README-Oeffnung und sichtbare Missing-Warnung. Zieltest `1 passed in 1.37s`,
kein Produktcodeedit. Frozen-/Installer-Bundle und realer OS-Viewer bleiben
STAB-6-Livegate. Status `target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-24-about-documentation-2026-08-27.md`.

Control #23 ist elementgenau belegt: echter ABCompareDialog erzeugt sichtbaren/
aktiven Accent-Button `Vergleich ausfuehren`. Echte QTest-Mausclicks erreichen
realen Scorer-/Ergebnisrenderpfad bei isoliertem DB-Loader sowie sichtbaren
Fehlerpfad. Zieltests `2 passed in 1.30s`, kein Produktcodeedit. Echter
Projekt-/DB-Liveworkflow bleibt offen. Status `target-test-pass-live-pending`.
Evidence:
`docs/superpowers/synthesis/stab5-control-23-ab-compare-run-2026-08-27.md`.

Control #22 ist elementgenau belegt: echter PBWindow-Build erzeugt genau eine
sichtbare/aktive Window-QAction `Speichern` mit StandardKey.Save und Window-
Parent. QAction-Trigger erreicht exakt das echte ProjectManagementController-
Objekt. Zieltest `1 passed in 9.44s`, kein Produktcodeedit. Reale
Projektpersistenz und physischer Ctrl+S-App-Livepfad bleiben offen. Status
`target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-22-save-action-2026-08-27.md`.

Control #21 ist elementgenau belegt: echter PBWindow-Build erzeugt genau eine
sichtbare/aktive Window-QAction `Redo` mit StandardKey.Redo und Window-Parent.
Vorab undone MarkerCommand im echten Timeline-QUndoStack wird durch
QAction-Trigger von 0 auf 1 wiederhergestellt; Stack danach undo-faehig.
Zieltest `1 passed in 11.05s`, kein Produktcodeedit. Physischer Redo-Shortcut-
App-Livepfad bleibt offen. Status `target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-21-redo-action-2026-08-27.md`.

Control #20 ist elementgenau belegt: echter PBWindow-Build erzeugt genau eine
sichtbare/aktive Window-QAction `Undo` mit StandardKey.Undo und Window-Parent.
MarkerCommand im echten Timeline-QUndoStack wird durch QAction-Trigger von 1
auf 0 zurueckgenommen; Stack danach redo-faehig. Zieltest `1 passed in 11.08s`,
kein Produktcodeedit. Physischer Ctrl+Z-App-Livepfad bleibt offen. Status
`target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-20-undo-action-2026-08-27.md`.

Control #19 ist elementgenau belegt: gefuelltes Recent-Projekte-Menu enthaelt
nach Projektaktion und Separator echte sichtbare/aktive QAction `Liste leeren`.
Trigger erreicht `_clear_recent_projects`, leert Store exakt einmal und zeigt
Erfolgsmeldung; Parent/Popup-Position belegt. Nur blockierendes `QMenu.exec`
bleibt isoliert. Zieltest `1 passed in 12.26s`, kein Produktcodeedit;
Echt-PBWindow-/Persistenz-Live bleibt offen. Status
`target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-19-recent-projects-clear-2026-08-27.md`.

Control #18 ist elementgenau belegt: `_show_recent_projects_menu()` erzeugt bei
gefuelltem RecentProjectsManager echte Projektaction mit Projektnamen als Text,
Pfad als Datenfeld, belegtem Parent/belegter Popup-Position und korrektem Trigger bis
`_open_recent_project`. Nur blockierendes `QMenu.exec` bleibt isoliert. Zieltest
`1 passed in 2.35s`, kein Produktcodeedit; Echt-PBWindow-Live bleibt offen.
Status `target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-18-recent-project-action-2026-08-26.md`.

Control #17 ist elementgenau belegt: `_show_recent_projects_menu()` erzeugt bei
leerem RecentProjectsManager genau eine sichtbare, deaktivierte QAction
`(Keine letzten Projekte)` mit Window-Parent und korrekter Popup-Position am
Tools-Button. Echte QMenu/QAction; nur modales `exec` isoliert. Zieltest
`1 passed in 1.35s`, kein Produktcodeedit. Echtes PBWindow-Popup bleibt offen;
Status `target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-17-recent-projects-empty-2026-08-26.md`.

Control #16 ist elementgenau belegt: echter WorkspaceSetupController baut
sichtbaren/aktiven `Tools`-Button samt produktivem QMenu. `_btn_recent` zeigt
auf denselben Button; erster Menuabschnitt enthaelt Tasks/Log/KI-Chat. Echter
Mausclick oeffnet das Menu sichtbar. Zieltest `1 passed in 2.15s`, kein
Produktcodeedit. PBWindow-/vollstaendige Menue-Liveauswahl bleibt offen; Status
`target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-16-tools-menu-button-2026-08-26.md`.

Control #15 ist elementgenau belegt: echter WorkspaceSetupController baut
sichtbare Tools-QAction `KI Chat anzeigen` und versteckten KI-Chat-Proxy.
QAction triggert Proxy; PBWindow-Routing oeffnet ContextPanel/Dock und aktiviert
den produktiv durch PanelSetupController gemounteten `CHAT`-Tab. Zieltest
`1 passed in 11.10s`, kein Produktcodeedit. PBWindow/ChatDock/LLM-Live bleibt
offen; Status `target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-15-chat-display-2026-08-26.md`.

Control #14 ist elementgenau belegt: echter WorkspaceSetupController baut
sichtbare Tools-QAction `Log anzeigen` und versteckten Konsole-Proxy. QAction
triggert Proxy; PBWindow-Routing oeffnet ContextPanel/Dock und aktiviert den
produktiv durch PanelSetupController gemounteten `LOG`-Tab. Geschaerfter
Zieltest `1 passed in 4.15s`, kein Produktcodeedit. PBWindow-Vollstart bleibt
offen; Status `target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-14-log-display-2026-08-26.md`.

Control #13 ist elementgenau belegt: echter WorkspaceSetupController baut
sichtbare Tools-QAction `Tasks anzeigen` und versteckten Tasks-Proxy. QAction
triggert Proxy, PBWindow-Tabrouting oeffnet ContextPanel/Dock und aktiviert
`Tasks`; Proxy bleibt unsichtbar. Gezielter Test `1 passed in 11.74s`,
Nachreview PASS, kein Produktcodeedit. Echter PBWindow-Vollstart bleibt offen;
Status `target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-control-13-tasks-display-2026-08-26.md`.

Control #12 ist elementgenau belegt: echter Produktbuilder/Wiring und sichtbarer
`Einstellungen`-Button erreichen per zwei Mausclicks echten
ProjectManagement-Handler. Je Click: eigener Dialog, korrekter Parent,
Ollama-Signalconnect, exec und deleteLater; `1 passed in 1.27s`, Reviews PASS.
Echter Dialoginhalt/QSettings/Modal-Live offen. Evidence:
`docs/superpowers/synthesis/stab5-control-12-settings-button-2026-08-26.md`.

Control #1 F1 besitzt jetzt elementgenauen Qt-Key→Handler→Dialogbeleg:
`1 passed in 2.10s`, drei Parallelreviews ohne Produktfinding, kein Codeedit.
Echter PBWindow-App-Lauf bleibt offen; Matrixstatus
`target-test-pass-live-pending`. Evidence:
`docs/superpowers/synthesis/stab5-controls-1-2-shortcut-help-2026-08-26.md`.

Controls #168/#169 sind manuell als `legacy-hidden / manual-excluded`
klassifiziert: nicht gemountet, explizit versteckt, aktiver Videopfad nutzt
Scroll + `fetchMore()`. Kein sichtbarer App-Bug, kein Produktcode-Fix und kein
Testlauf. Matrix besitzt nach B-903-Nachzug 0 `unresolved`-Zeilen. Evidence:
`docs/superpowers/synthesis/stab5-controls-168-169-video-pagination-2026-08-26.md`.

Der frühere strenge Review materialisierte 36 Lücken nicht einzeln. Nach
Matrixreihenfolge ist #1 der erste verbleibende `no-candidate`-Eintrag.

B-903 / Controls #213/#214 sind code-complete: sichtbare Schnitt-Preview-
Buttons mit bestehender API verbunden, Statuslabel/Symbol synchronisiert.
RED→GREEN-Zieltest, Syntax, Diffcheck und Parallelreview sind gruen. Echter
Medien-/App-Livepfad fehlt; Status bleibt
`code-fix-pending-live-verification`. Evidence:
`docs/superpowers/synthesis/stab5-control-213-schnitt-play-2026-08-26.md`.

Reihenfolgekorrektur: #168/#169 stehen in vollständiger Matrix vor #213/#214.
#213 war wegen truncierter Ausgabe irrtümlich als erster unresolved-Rest
gewählt worden. Nach Abschluss der bereits aktiven B-903-Task geht Arbeit
zurück auf #168.

B-901 ist code-complete: Versionspruefung im Defaultpfad aktiviert, kanonische
GitHub-API korrigiert, Override erhalten. Zwei Zieltests, Syntax und Diffcheck
sind gruen. Echter App-/Release-Bannerpfad fehlt; Status bleibt
`code-fix-pending-live-verification`. Evidence:
`docs/superpowers/synthesis/b901-update-controls-default-2026-08-26.md`.

Governance-/Planhygiene-Folgebereinigung ist documentation-complete. Evidence:
`docs/superpowers/synthesis/plan-handoff-vault-authority-cleanup-2026-08-26.md`.

B-900 ist nach echtem First-Run-App-Pfad `fixed`: isolierter Modal-Wizard,
echter QThread und Connection-Refused-Fehler ergaben Modell/Gesamt 0 Prozent,
roten Fehlertext und korrekte Finish-Meldung. STAB-5 selbst bleibt offen,
weil sein DoD je Element einen Testbeleg verlangt; statische Verdrahtung allein
reicht nicht. Evidence:
`docs/superpowers/synthesis/b900-setup-wizard-progress-truth-2026-08-26.md`.

DoD-Abgleich fand 190 UI-Testdateien und 142 Synthesen, aber keine stabile
elementgenaue Zuordnung. Die alte Zahl 182 war nur eine Constructor-Site-Zahl
und ist als Controlwert verworfen. Factory-Expansion liefert 222 statische
Deklarationsstellen, keine Runtime-Widgetzahl. STAB-5 bleibt `in_progress`.
Evidence:
`docs/superpowers/synthesis/stab5-ui-action-evidence-2026-08-26.md`.

Read-only-Evidenzreview widerlegte automatische Testtreffer als Belege und
fand B-901 (Update-Controls default unerreichbar) sowie B-902 (About-
Dokumentation im installierten Build stiller No-Op). Evidence:
`docs/superpowers/synthesis/stab5-ui-evidence-cleanup-2026-08-26.md`.

STAB-5-Rohinventar ist statisch abgeschlossen: 103 UI-Dateien, 182 rohe
Constructor-Sites, 636 Signalverbindungen und 25 Cross-File-Kandidaten. Alle
direkten Actions/Handler sind verdrahtet. Neues High-Finding B-900: Setup-
Wizard zeigt bei `ok=False` rote Fehlerzeile, setzt Modell- und Gesamtbalken
aber dennoch auf 100 Prozent. Evidence:
`docs/superpowers/synthesis/stab5-ui-action-inventory-2026-08-26.md`.

STAB-4 wurde vom User am 2026-08-26 als Phase bestaetigt. Folgephasen duerfen
autonom fortgesetzt werden; ihr Abschlussmarker wird trotzdem erst nach dem
jeweiligen Nachweis geschrieben. B-774s seltener echter Kontexttod bleibt als
nicht erneut beobachtete Grenze dokumentiert.

STAB-3 ist `agent-complete-await-user-marker`. Aktueller qwen2.5-ChatDock-
Toolpfad lieferte Learn, Recall, Stats und Explain real; B-896 Commit
`90e1472`, B-897 Commit `50ce61d`. Non-Tool besitzt User-`fixed` B-738,
echten headless Learn-/Recall-Beleg vom 2026-08-11 und aktuellen fokussierten
Regressionstest. Ein erneuter Non-Tool-ChatDock-Lauf wurde nach Gemma-FAIL
gemaess Useralternative "besseres LLM oder ueberspringen" uebersprungen und
ist nicht als Live-PASS markiert. Evidence:
`docs/superpowers/synthesis/stab3-llm-paths-2026-08-25.md`. Kein
User-`fixed`-/STAB-3-Phasenmarker. B-723 Lockscope/Cancel/Projektwechsel/DB
agentseitig live belegt; enger Exception-Frame-Cleanup-Fix implementiert und
live nachgeprueft.
STAB-4-Kaltbaseline-VRAM-Gate bleibt rot (+813 statt maximal +512 MiB).
Evidence: `docs/superpowers/synthesis/stab4-b723-gpu-cancel-project-switch-2026-08-25.md`.
B-725 Copy-/GPU-Parallelitaet, Cancel, FFmpeg-Cleanup und DB agentseitig live
belegt; kein neuer Produktcodefix. Evidence:
`docs/superpowers/synthesis/stab4-b725-copy-concurrency-2026-08-25.md`.
B-726 oeffentliche RAFT-API real auf GTX 1060/cuda:0 belegt: 220
Konkurrenzversuche blockiert, 0 Lock-Erwerbungen waehrend Load/Inferenz/Unload;
Lock danach frei. Evidence:
`docs/superpowers/synthesis/stab4-b726-raft-direct-live-2026-08-25.md`.
Externer Ollama-Ownershippfad real belegt: nativer App-Shutdown beendete App
PID 3392, liess externen Serve PID 1464 samt HTTP-200-API unangetastet; DB
und Cleanup gruen. Evidence:
`docs/superpowers/synthesis/stab4-ollama-ownership-races-2026-08-25.md`.
App bleibt nach Shutdown-Test geschlossen. Ollama PID 1464 ueberlebte den
direkten Postcheck, war beim spaeteren Recheck 22:09 aber beendet; Ursache
unbekannt, kein PB-Studio-Prozess lief mehr. Kein Push.

Der STAB-4-Kombinationszyklus ist agentseitig live ausgefuehrt: Preview,
qwen2.5-Chat, htdemucs-Cancel, SigLIP-/RAFT-Video-Cancel, echter
`h264_nvenc`-Export-Cancel, Projektwechsel unter isoliertem Root-Scope und
native Shutdowns. Prozesse/Teiloutput wurden bereinigt, beide Test-DBs sind
`quick_check: ok`, Host-Settings blieben digestidentisch. Neuer B-898 bleibt
`open`: Export-Cancel startete noch einen Fallback/Precheck und endete erst
rund 13 Sekunden spaeter. Kalt-VRAM-Gate (+813 > +512 MiB), B-774 und
30-Minuten-Soak bleiben offen. Evidence:
`docs/superpowers/synthesis/stab4-combined-cycle-2026-08-25.md`.

30-Minuten-Idle-Soak ist agentseitig abgeschlossen: 361 Samples/30:00.5 min,
UI-Heartbeat max. 3.3 ms, Threads +2, RSS max. 449.4 MiB, Idle-VRAM 0 MiB,
keine DB-/Log-/Prozessfehler. Geschuetzte DBs: 15 Rohteile und 5 logische
DBs ohne Differenz. Isolierte Test-DB ist konsistent; erwarteter
`project_sources.last_seen_at`-Write plus WAL-Checkpoint erklaert Hashwechsel,
aber exakter 22:57-Vor-Digest fehlt. STAB-4 gesamt bleibt wegen Kalt-VRAM,
B-774 und B-898 offen/rot. Evidence:
`docs/superpowers/synthesis/stab4-30min-soak-2026-08-25.md`.

B-898 ist `agent-fixed-await-user`: Cancel wird ueber den gesamten
Export-/FFmpeg-Pfad als `ExportCancelled` propagiert; LUFS-Vor- und
Zwischenchecks brechen gleichartig ab. Echter `h264_nvenc`-xfade-Export wurde
ueber TASKS abgebrochen: kooperativer Abbruch und Worker-Ende in derselben
Sekunde, kein B-603-Fallback/Precheck, kein FFmpeg-/Teilfile-Rest, App
responsiv, DB `quick_check: ok`, nativer Shutdown ohne Prozessrest. Vier
gezielte Tests, PyCompile und fokussierter Ruff gruen. Kein User-`fixed`-
Marker. Evidence:
`docs/superpowers/synthesis/b898-export-cancel-no-fallback-2026-08-26.md`.
Naechstes konkretes rotes STAB-4-Gate: Kalt-VRAM +813 MiB statt maximal
+512 MiB. B-774-Realbeleg bleibt danach separat offen.

B-899 blockiert autonome Fortsetzung: isolierter echter `htdemucs`-CUDA-Lauf
liegt nach Loeschen aller Modell-/Tensorreferenzen, GC und doppeltem
`empty_cache()` bei 624 MiB globalem VRAM, obwohl Torch `allocated=0` und
`reserved=0` meldet. `ipc_collect()` aendert nichts; erst Prozessende bringt
0 MiB. Damit ist +512 MiB unter aktueller In-Process-Architektur bereits um
112 MiB unmoeglich. Technisch ehrliche Wege: Demucs-Out-of-Process
(Architekturumbau) oder Gate-Anpassung (Acceptance-Criteria-Aenderung). Keine
Option ohne Userentscheidung. Evidence:
`docs/superpowers/synthesis/b899-cold-vram-gate-decision-2026-08-26.md`.

Userentscheidung D-093: In-Process-Gate auf `Baseline +1024 MiB` erhoehen;
Out-of-Process-Demucs nicht umsetzen. Verbindliche Zusatzkontrollen:
Torch allocated/reserved nach Cleanup 0/0, kein wachsender VRAM-Rest ueber
Wiederholungsläufe, keine Zombie-/Kindprozesse. Naechste einzige Task ist
gezielter Wiederholungsbeleg; danach B-774-Realbeleg.

B-899 ist `agent-complete-await-user-marker`: zwei echte htdemucs-
Load+10-s-CUDA-Inferenz+Cleanup-Zyklen im selben Prozess hatten identische
Peaks 1944 MiB und identische Cleanup-Werte 1020 MiB bei Baseline 402 MiB
(Delta +618 MiB); Torch allocated/reserved nach beiden Zyklen 0/0, kein
Wachstum. Nach Prozessende 396 MiB und keine passenden Prozessreste. D-093-
Gate bestanden; kein User-`fixed`-Marker. Naechste einzige Task: B-774-
Realbeleg bewerten.

B-774-Evidenzbewertung agent-complete: Current 9/9 Fault-Injection; echter
Post-Fix-App-Lauf mindestens 100 RAFT-/SigLIP-GPU-Clips mit stabilen
25er-VRAM-Marken und weiteren erfolgreichen Clips. Mehrere Power-Resume-
Probes, folgende CUDA-Inferenzen gruen. Echter gestorbener Kontext trat nicht
erneut auf und wird nicht per riskantem Treiber-/Hardware-Reset erzwungen.
Evidence:
`docs/superpowers/synthesis/stab4-b774-evidence-evaluation-2026-08-26.md`.
STAB-4 ist `agent-complete-await-user-marker`; DoD:
`docs/superpowers/synthesis/phase-stab4-done-2026-08-26.md`.
Uservorgabe 2026-08-26: keine weiteren STAB-4-Tests; kuenftige Tests nur
minimal, direkt betroffen und am spaetestmoeglichen Endgate.

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
