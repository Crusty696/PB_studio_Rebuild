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
