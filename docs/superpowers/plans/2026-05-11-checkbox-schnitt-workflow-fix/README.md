# Checkbox + SCHNITT-Empty-State + Workflow-Fix — Implementation Plan

**Datum:** 2026-05-11
**Branch:** `feat/schnitt-redesign-2026-05-09` (weiter)
**Vorgeschichte:** Live-Test 2026-05-10 deckte vier neue echte Bugs auf. Phase A–E des pipeline-progress-wiring-fix-Plans war fertig, aber tiefere Probleme blieben:

- Audio-Checkbox + "Alle"-Button werden komplett ignoriert.
- SCHNITT-Empty-State-Preset → silent return ohne Worker.
- Cutliste / Cut-Edit-Affordances fehlen.
- Workflow-Reihenfolge im UI nicht erkennbar.

**Ziel:** Audio-Multi-Select via Checkbox funktioniert; SCHNITT-Preset-Klick startet wirklich Pipeline; Cutliste sichtbar; Workflow-Struktur klar.

**Adressiert:** B-293 (P0), B-294 (P0), B-295 (P1), B-296 (P1).

**Out of scope:** keine neue Pipeline-Architektur, keine Brain-V3-Änderungen, keine LOCKED-Architektur-Touches.

---

## ⛔ HARTE REGELN — gelten für jede Sub-Task

Übernimmt R-1 bis R-12 aus `docs/superpowers/plans/2026-05-10-pipeline-progress-wiring-fix/README.md` verbatim. Plus drei neue Regeln gegen das hier gefundene "halbverdrahtet"-Muster.

### R-1 — "Tests grün ≠ Done"

Phase fertig nur wenn: Unit-Tests grün + Production-Boot-Smoke grün + User-Live-Walk im laufenden GUI.

### R-2 — Kein neuer Slot ohne Production-Wiring-Grep > 0

### R-3 — Worker-Progress muss UI-Progress berühren

### R-4 — `min(99, ...)`-Cap nur mit 100%-Tick davor

### R-5 — Kein Step gilt als "done" ohne explizites `mark_done`

### R-6 — `infer_from_db` als Fallback, nicht als Ersatz

### R-7 — Vault-Pflicht pro Sub-Task

### R-8 — Conventional Commits, atomar, deutsch, Subject ≤ 50 Zeichen

### R-9 — Conda-Env hart: `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`

### R-10 — Stop-and-Ask bei Unklarheit

### R-11 — UI-Live-Beobachtung als Phase-Done-Beweis

### R-12 — Audit-Greps müssen am Ende leer sein

### R-13 (NEU) — Selection-Helper-Symmetrie zwischen Audio und Video

Wenn `video_analysis` einen Helper `_get_selected_*` mit Checkbox-First-Logik nutzt, muss das `audio_analysis`-Pendant dieselbe Logik haben. Source-Inspection-Regel: für jede `_get_selected_*`-Methode in einem Controller muss `get_checked_ids` referenziert sein **bevor** `selectionModel().selectedRows()` gerufen wird. Pre-Commit-Grep:

```bash
# Beide Helper muessen get_checked_ids enthalten
grep -n "def _get_selected" ui/controllers/audio_analysis.py
grep -nA 20 "def _get_selected" ui/controllers/audio_analysis.py | grep "get_checked_ids"
grep -nA 20 "def _get_selected" ui/controllers/video_analysis.py | grep "get_checked_ids"
```

### R-14 (NEU) — Kein silent return im Worker-Trigger-Pfad

Wenn ein Controller-Slot einen Worker startet und dafür Voraussetzungen prüft (Audio-Selection, Video-Selection, Projekt-State), darf bei Fehlbedingung **nicht** still returnt werden. Pflicht:

- Klare User-Nachricht in Konsole + StatusBar.
- Loading-State (falls aktiv) wird kontrolliert auf empty oder editor zurückgesetzt.
- Optional: automatischer Recovery-Pfad (z. B. Auto-Fill aus Projekt-DB).

Pre-Commit-Pattern: in jedem Slot, der `worker.start()` oder `_start_worker_thread(worker)` ruft, muss ein "Pre-Flight"-Block sichtbar sein.

### R-15 (NEU) — Doppel-Aliase-Verbot

Wenn zwei Buttons auf denselben Handler verdrahtet sind (e.g. `btn_motion_analysis.clicked.connect(_start_video_pipeline)` UND `btn_video_pipeline.clicked.connect(_start_video_pipeline)`), sind sie funktionale Duplikate. Verbot:

- Entweder: Alias-Button entfernen.
- Oder: Alias-Button visuell als "Detail-Klick" gestylt + Tooltip "Wird vom Pipeline-Button mit erledigt".

Pre-Commit-Grep:

```bash
# Suche Doppel-Connects auf dieselbe Handler-Methode
grep -n "_start_video_pipeline" ui/controllers/workspace_setup.py
```

Wenn > 1 Treffer in `workspace_setup.py`: dokumentieren warum (Plan-Abweichungs-Register).

---

## ⛔⛔ ZWANGS-REGELN gegen Abweichung / Skip / Eigenmächtigkeit

User-Forderung 2026-05-11: Plan muss so streng sein dass Agent **keine** Möglichkeit hat, vom Plan abzuweichen, etwas auszulassen, zu überspringen oder anderes zu tun als geplant. Agent muss seine eigene Arbeit gegenprüfen, validieren, bei Abweichung **automatisch und bevor er zur nächsten Aufgabe geht** korrigieren, nochmals prüfen + validieren + verifizieren bis es stimmt und funktioniert.

### R-16 — Plan-Treue-Pflicht: Pre-Task Soll-Snapshot

**Vor jedem Code-Touch** muss der Agent (oder dispatchender Subagent) explizit als ersten Schritt einen **Soll-Snapshot** in den Task-Report schreiben:

```markdown
## Soll-Stand fuer Task X
1. Datei `<pfad>` — Zeile <X> bis <Y> — Methode `<name>` — exakt diese Aenderung: <kurz>.
2. Datei `<pfad>` — neue Methode `<name>` — Signatur `<sig>`.
3. Test-Datei `<pfad>` — neu mit <N> Tests.

## Pre-Task Git-Status-Snapshot
- HEAD: <SHA>
- Erwartete neue Files: [...]
- Erwartete geaenderte Files: [...]
- KEINE anderen Files duerfen geaendert werden.
```

Nach Implementation: **Ist-Snapshot** anhand `git status` + `git diff --stat`. Diff Soll/Ist explizit ausweisen. Bei Abweichung → R-17 greift.

### R-17 — Selbst-Validierungs-Schleife (Auto-Correct vor DONE)

Nach Implementation MUSS der Agent eine **Selbst-Validierung** gegen den Soll-Stand machen:

```markdown
## Spec-Compliance-Check (selbst)
| Plan-Punkt | Soll | Ist | OK? |
|---|---|---|---|
| Task A.1 failing test | 3 Tests in <datei> | 3 Tests in <datei> | ✓ |
| Task A.2 Helper Body | <code-snippet> | <ist-code> | ✓ oder ✗ |
| ... | | | |
```

Bei JEDEM `✗` MUSS der Agent **bevor er DONE meldet**:

1. Den Fehler benennen (was weicht ab).
2. Korrigieren — sofort, gleicher Subagent, kein neuer Task.
3. Selbst-Validierung erneut laufen.
4. Erst wenn alle Punkte `✓`: DONE-Report.

Maximum **3 Iterationen** Selbst-Korrektur. Danach BLOCKED — keine versteckte Aufgabe.

### R-18 — Drei-Pass-Verifikation pro Task

Vor DONE-Report MÜSSEN ALLE DREI Verifikationspässe grün sein:

**Pass 1 — Source-Inspection**: AST/Grep dass Implementation den Plan-Code enthält.

**Pass 2 — Behavior-Test**: pytest grün; bei UI-Wirkung zusätzlich qapp-Fixture-Test.

**Pass 3 — Live-Boot-Smoke** (wenn Task UI/Worker berührt): Mini-Skript fährt echtes PBWindow hoch und prüft die konkrete Wirkung.

Wenn EIN Pass rot: zurück zu Implementation (R-17-Schleife). Kein DONE.

Pre-Commit-Pflicht: alle drei Pass-Ergebnisse im Commit-Body protokollieren als Tabelle.

### R-19 — Kein DONE_WITH_CONCERNS

Status-Werte für Subagent-Reports sind ausschließlich:

- **DONE** — alle drei Pässe grün, Spec-Compliance-Check 100% `✓`.
- **BLOCKED** — drei Iterationen R-17 erschöpft oder externe Sache (DB-Schema, Hardware, fehlende Dependency).
- **NEEDS_CONTEXT** — Plan-Text unklar, Subagent fragt Controller.

**DONE_WITH_CONCERNS ist verboten.** "Concerns" sind Bugs. Vor DONE müssen sie gefixt sein. Subagent darf keine Compromise-Status melden.

### R-20 — Anti-Skip-Checkliste

Jeder Task im Plan hat eine nummerierte Checkliste mit `- [ ]`. Vor DONE muss der Subagent jeden Punkt mit Beleg abhaken:

```markdown
## Task A.X Checkliste
- [x] Test geschrieben (`tests/...`) — siehe Commit `<SHA>`
- [x] Test gelaufen RED — Output: `FAILED ...`
- [x] Implementation in `<file>` Z.<a>-<b> — Diff: `git show`
- [x] Test gelaufen GREEN — Output: `PASSED ...`
- [x] Regression-Sweep gruen — Output: `<N> passed`
- [x] Vault-Update — `wiki/bugs/<B>.md` updated
- [x] log.md-Eintrag — append confirmed
- [x] Commit erstellt — SHA `<...>`
- [x] R-18 Drei-Pass-Verifikation — alle drei gruen
- [x] R-17 Spec-Compliance 100% — keine `✗`
```

Kein Punkt darf ungehakt sein. Skip = BLOCKED + Re-Dispatch.

### R-21 — Pre/Post-Git-Status-Audit

Vor Task: `git status --porcelain` Snapshot. Erwartete neue/geänderte Files in Soll-Liste.

Nach Task: `git status --porcelain` erneut. Diff:

- Erwartete Files vorhanden? ✓
- Unerwartete Files dabei? **Auto-Revert** oder explizite Erlaubnis vom Controller. Niemals stillschweigend mitcommitten.
- Erwartete Files fehlen? BLOCKED.

Im Commit-Body Tabelle:

```markdown
## Git-Status-Audit
| File | Soll | Ist |
|---|---|---|
| `tests/ui/test_x.py` | NEW | NEW ✓ |
| `ui/controllers/x.py` | MODIFIED | MODIFIED ✓ |
| `<unerwartete>` | — | DROPPED ✓ |
```

### R-22 — Pre-Commit Audit-Greps blocken Commit

Vor jedem `git commit` MUSS der Subagent die Plan-spezifischen Audit-Greps (R-13/R-14/R-15 plus task-spezifische) laufen lassen. **Wenn ein Soll-Wert nicht erreicht ist: kein Commit.** Output ins Commit-Body als Beleg.

Beispiel für Phase A:

```bash
# R-13 Audio-Helper-Symmetrie
grep -nA 25 "def _get_selected_audio_track" ui/controllers/audio_analysis.py | grep "get_checked_ids" || exit 1
grep -nA 25 "def _get_selected_audio_tracks" ui/controllers/audio_analysis.py | grep "get_checked_ids" || exit 1
```

Bei `exit 1`: Subagent dokumentiert das im Report als BLOCKED und stoppt. Kein Commit-Workaround.

### R-23 — Reviewer-Findings sind MUST-FIX, kein "follow-up later"

Code-Quality-Reviewer-Subagenten dürfen Issues in 4 Kategorien melden:

- **Critical** — Production-Bug oder Datenverlust-Risiko. **MUST-FIX vor DONE des Tasks.**
- **Important** — Bug oder UX-Loch. **MUST-FIX vor DONE des Tasks.**
- **Minor** — Stil/Naming/Magic-Number. **MUST-FIX vor DONE des Tasks** falls < 5 min, sonst in Follow-up-Bug.
- **Info** — Beobachtung ohne Action.

**Kein "wird in nächstem Plan gefixt" mehr.** Wenn Reviewer Important findet → Implementer fixt → Reviewer re-reviewt → erst dann DONE.

### R-24 — Final-Phase-Validation: Plan-vs-Realität-Diff

Am Ende jeder Phase (bevor Status auf complete) muss ein **Phase-Audit-Subagent** dispatched werden, der das gesamte Phase-Soll gegen den Commit-Stream prüft:

- Wurden ALLE Tasks der Phase committet?
- Stimmen Commit-Hashes mit Bug-File-Frontmatter überein?
- Liefert `git log <BASE>..<HEAD>` exakt die geplanten Commits?
- Source-Inspection: enthält der Code wirklich was der Plan vorgibt?

Audit-Output als Vault-Synthesis `wiki/synthesis/phase-<X>-audit-YYYY-MM-DD.md`. Bei Abweichung: Phase NICHT abschließbar, zurück zu fehlendem Task.

### R-25 — User-Approval-Gate vor Phase-Wechsel (optional)

Falls Plan-Phase besonders riskant (Layout-Refactor, DB-Schema, LOCKED-Berührung): Controller schaltet auf "Pause-vor-naechster-Phase" und meldet User Status mit der Frage "Phase X done — Phase Y starten?". Erst nach explicit "go" weiter.

Im Default-Modus: nahtloser Übergang ohne Pause (Subagent-Driven-Skill ohnehin schon Standard).

---

## Konsequenzen der Zwangs-Regeln

- Jeder Subagent-Implementer-Prompt MUSS auf R-16..R-24 verweisen.
- Jeder Spec-Reviewer-Prompt MUSS R-17/R-18-Schleife prüfen ob durchlaufen.
- Jeder Code-Quality-Reviewer-Prompt MUSS R-23 zitieren (alle Issues MUST-FIX).
- Implementer der `DONE_WITH_CONCERNS` zurückmeldet wird sofort mit BLOCKED-Note re-dispatched: "R-19 — DONE_WITH_CONCERNS verboten. Fix die Concerns, dann DONE."
- Implementer der R-20-Checkliste nicht abhakt wird ebenfalls re-dispatched.

Diese Verschärfung erhöht den Aufwand pro Task um ~20% (zusätzliche Self-Validation-Pässe + Auto-Correct-Schleifen), reduziert aber die Zahl der Reviewer-Findings drastisch und verhindert die "halbverdrahtet"-Klasse Bugs, die in den vorigen Phasen wiederholt aufgetreten ist.

---

## Phasen-Übersicht

| # | Phase | Zweck | Aufwand | Bugs |
|---|---|---|---|---|
| A | Audio-Checkbox-Helper | `_get_selected_audio_track` + `_get_selected_audio_tracks` (Plural) checkbox-first. | 45–60 min | B-293 |
| B | Audio-Slots umstellen | 8 Audio-Buttons + 2 Stems-Calls auf neue Helper. | 30 min | B-293 |
| C | SCHNITT Empty-State Recovery | `_ensure_combos_filled_from_project` + Adapter-Slot-Pre-Flight. Kein silent return mehr. | 60 min | B-294 |
| D | Cutliste-Widget | `CutListPanel` neu im Sub-Tab "Schnitt" oder eigener Sub-Sub-Tab. Refresh bei Auto-Edit-Done. | 90–120 min | B-295 |
| E | Workflow-Struktur | MEDIA-Workspace in 3 Sub-Sektionen; Doppel-Buttons entfernen; Cockpit-Card-Klick navigiert. | 90–120 min | B-296 |
| F | Onboarding-Banner | Pro Workspace kontextueller Hinweis-Banner mit "nächster Schritt"-Empfehlung. | 60 min | B-296 |
| G | Integration-Smoke-Tests | Audit-Greps R-13/R-14/R-15 + Live-Boot-Smoke. | 45 min | Schutz |
| H | User-Live-Verify | 10-Punkte-Drehbuch. | User-Zeit | Abnahme |

Total Agent: ~7–9 h. User-Live-Verify: ~20 min.

---

## Globaler Erfolgs-Test

User startet App, importiert Solo_Natur + Crusty Progressive Psy Set2.mp3:

1. MATERIAL-Tab: Audio-Pool — alle Tracks ankreuzen via "Alle" → "Audio analysieren" → alle Tracks werden analysiert. **Maus-Selection irrelevant.**
2. Video-Pool: Checkbox "Alle" → "Video-Pipeline" → alle Videos analysiert.
3. SCHNITT-Tab: Empty-State → "Techno"-Klick → Loading → Editor mit Timeline + Cutliste.
4. Cutliste rechts/unten sichtbar mit Spalten Zeit/Quelle/Lock.
5. PROJEKT-Tab: Cockpit-Card "Video" blocked → Klick → springt zu MATERIAL > Video-Sektion.
6. MEDIA: Sub-Sektionen "1. Import / 2. Analyse / 3. Convert" visuell getrennt.
7. Onboarding-Banner zeigt nächste Aktion bei jedem Tab-Wechsel.
8. Keine Doppel-Aliase: `btn_motion_analysis` + `btn_siglip_embeddings` entweder weg oder visuell als Sub-Step.
9. EXPORT: Render läuft, Datei spielbar.
10. Re-Open Project: Cutliste persistiert.

10/10 ✅ → User vergibt `status: fixed` an B-293/B-294/B-295/B-296.

---

## Risiken & Trade-Offs

| ID | Risiko | Gegenmaßnahme |
|---|---|---|
| W-1 | MediaTableModel hat unterschiedliche Checkbox-APIs für video_pool und audio_pool | Source-Inspection beider Models in Phase A vor Code-Change |
| W-2 | Auto-Fill in Combos: was wenn Projekt mehrere Audios hat? | Erstes nehmen + Konsolen-Hinweis "Wechsle Audio manuell wenn gewünscht" |
| W-3 | Cutliste-Widget braucht TimelineEntry-Adapter | Bestehende `TimelineEntry`-Schema lesen; Cutliste rendert pro Entry, nicht pro `CutPoint` |
| W-4 | MEDIA-Layout-Refactor bricht bestehende Promotions in workspace_setup | Promotions unverändert lassen, nur Layout-Container reorganisieren |
| W-5 | Onboarding-Banner persistiert via QSettings → kollidiert mit existierender Schema-Migration | Eigener Settings-Key, nicht in existierenden Migrationspfaden |

---

## Anti-Patterns (Verbot)

- Silent return im Worker-Trigger-Pfad (R-14).
- Doppel-Aliase ohne Dokumentation (R-15).
- Audio-Helper ohne `get_checked_ids` (R-13).
- "Sollte funktionieren"-Behauptungen ohne Live-Test.
- `status: fixed` durch Agent.
- Skill-Auto-Trigger anderer Skills.
- Force-Push, destruktive Git-Aktionen, DB-Schema-Aenderungen ohne explizite User-Freigabe.

---

## Plan-Anker

- Bug-Files: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-293..B-296*.md`.
- Vorgänger-Plan: `docs/superpowers/plans/2026-05-10-pipeline-progress-wiring-fix/`.
- Test-Datensatz: Solo_Natur (103 Videos) + Crusty Progressive Psy Set2.mp3 (149 MB).
- Conda-Env: `C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe`.

---

## Freigabe

Plan-Status: **draft, awaiting user approval**.

Agent rührt keinen Code an, bis User explizit "start Phase A" / "Plan freigegeben" sagt.

Bite-sized TDD-Task-Plan folgt in `IMPLEMENTATION_PLAN.md` nach Plan-Freigabe.
