# Phase 12.3 — Live-Verifikation (User-Aktion)

**Phase:** SCHNITT Workspace Redesign — Phase 12, Task 12.3
**Datum erstellt:** 2026-05-09
**Status setzen:** **Nur User**, nicht Agent.

---

## Ziel

Manuelle End-to-End-Verifikation des SCHNITT-Workspace-Redesigns mit echtem Test-Datensatz. Jeder Schritt hat eine konkrete Erwartung. Bei Abweichung: Bug-File anlegen.

---

## Voraussetzungen

- **Branch aktiv:** `feat/schnitt-redesign-2026-05-09`
- **Phase 11 grün:** alle Tests aus `tests/test_services/`, `tests/ui/` (ohne `gui/e2e/slow`-Marker) laufen — pre-existing Fail B-222a (`tests/test_services/test_b222_model_warmup.py::test_b222a_pipeline_worker_has_preflight`) ist erlaubt.
- **Phase 12.1 committed:** `btn_toggle_inspector` Tot-Code entfernt (siehe Phasen-Plan).
- **Phase 12.2 verschoben:** EditWorkspace-Sunset wird separater Folge-Plan (siehe `12_CLEANUP_AND_VERIFY.md` Task 12.2).

---

## Test-Datensatz

Aus User-Memory (`reference_test_dataset.md`):

- **Video-Ordner:** `C:\Users\David Lochmann\Documents\Solo_Natur-20260406T220640Z-3-001\Solo_Natur` (103 Files)
- **Audio:** `Crusty Progressive Psy Set2.mp3` (149 MB DJ-Mix, Pfad zur Wahl des Users)

---

## App-Start

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" main.py
```

Aus dem Repo-Root: `C:\Users\David Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild`.

---

## Klickfolge — 16 Schritte

### Schritt 1 — Projekt anlegen

- **Aktion:** PROJEKT-Tab → Neues Projekt anlegen, Name: `Schnitt-Verify-2026-05-09`.
- **Erwartung:** Projekt erscheint in Projekt-Liste, ist aktiv geladen.

### Schritt 2 — Audio importieren + analysieren

- **Aktion:** MATERIAL & ANALYSE-Tab → Audio-Import: `Crusty Progressive Psy Set2.mp3` → BPM/Beats analysieren → Stems separieren.
- **Erwartung:** BPM-Wert + Beat-Count erscheinen, Stems-Status grün (drums, bass, other, vocals).

### Schritt 3 — Video-Folder importieren

- **Aktion:** Video-Import → Folder-Import auf `Solo_Natur`.
- **Erwartung:** 103 Clips erscheinen in der Material-Liste, Thumbnails laden.

### Schritt 4 — Video-Pipeline starten

- **Aktion:** Video-Pipeline-Knopf drücken, warten bis Progress grün.
- **Erwartung:** Alle 103 Clips analysiert (Embedding, Motion, Aesthetic), keine Fehler-Toasts.

### Schritt 5 — SCHNITT-Tab öffnen

- **Aktion:** SCHNITT-Tab klicken.
- **Erwartung:** **Empty State** sichtbar — 4 Preset-Buttons (Techno, Cinematic, Vlog, Documentary o.ä.). Keine Sub-Tabs sichtbar.

### Schritt 6 — Techno-Preset auslösen

- **Aktion:** Button „Techno" klicken.
- **Erwartung:** **Loading State** mit rotierendem Status-Label. Reihenfolge:
  1. „Analysiere Audio…"
  2. „Setze Schnitte…"
  3. „Wähle Clips aus…"

### Schritt 7 — Editor State erscheint

- **Aktion:** Warten bis Auto-Edit fertig.
- **Erwartung:** **Editor State** mit Sub-Tabs erscheint. Aktiv: Sub-Tab „Schnitt". Inspector-Tab rechts gefüllt mit Default-Auswahl.

### Schritt 8 — Clip-Inspect

- **Aktion:** Im Sub-Tab „Schnitt" einen beliebigen Clip auf der Timeline klicken.
- **Erwartung:** Inspector zeigt Detail-Felder dieses Clips (Quelle, In/Out, Dauer, Tags).

### Schritt 9 — Lock-Toggle

- **Aktion:** Auf das Lock-Icon eines Clips klicken.
- **Erwartung:** Goldrand erscheint um den Clip, Schloss-Icon wechselt von offen → geschlossen (gefüllt).

### Schritt 10 — Pacing-Tab + Re-Generate auslösen

- **Aktion:** Sub-Tab „Pacing & Anker" öffnen → `energy_reactivity` auf **80** → `cut_rate_combo` auf **2 Beats** → Button „Mit neuen Pacing-Einstellungen generieren" klicken.
- **Erwartung:** **QMessageBox** Dialog erscheint mit Text:
  > „Achtung: Dies überschreibt aktuelle ungelockte Schnitte. Fortfahren?"

### Schritt 11 — Yes → Re-Generate respektiert Lock

- **Aktion:** Im Dialog auf „Yes" klicken.
- **Erwartung:** Erneut **Loading State**, danach **Editor State**. Der in Schritt 9 gelockte Clip ist **noch da** (gleiche Position, Goldrand). Ungesperrte Clips wurden ersetzt.

### Schritt 12 — Audio-Tab gefüllt

- **Aktion:** Sub-Tab „Audio" öffnen.
- **Erwartung:** Waveform sichtbar, Stems-Mixer-Slider vorhanden, LUFS-Wert + Tonart befüllt.

### Schritt 13 — RL & Notes Autosave

- **Aktion:** Sub-Tab „RL & Notes" öffnen → in Notes-Editor schreiben: `Test 2026-05-09 Schnitt-Verify`. **1 s warten**.
- **Erwartung:** Footer-Label zeigt „Zuletzt gespeichert: HH:MM:SS" (aktuelle Uhrzeit).

### Schritt 14 — Notes Persistenz nach Reload

- **Aktion:** App schließen → erneut starten → Projekt `Schnitt-Verify-2026-05-09` laden → SCHNITT → Sub-Tab „RL & Notes".
- **Erwartung:** Notes-Inhalt aus Schritt 13 erscheint exakt wie gespeichert.

### Schritt 15 — Combo-Wheel-Schutz

- **Aktion:** Mauszeiger über `cut_rate_combo` bewegen, **ohne zu klicken**, Mausrad scrollen.
- **Erwartung:** Wert ändert sich **nicht**. (Phase-9-Schutz gegen versehentliches Wheel-Triggern.)

### Schritt 16 — Undo

- **Aktion:** Strg+Z drücken.
- **Erwartung:** Letzte Aktion wird rückgängig gemacht (z.B. Lock-Toggle aus Schritt 9 → Lock entfernt, Goldrand weg). Falls Strg+Z keine Aktion trifft: Undo-Stack ist leer ⇒ ggf. eigene Klick-Aktion zwischen Schritt 11 und 16 als Test einfügen.

---

## Befunde dokumentieren

### Erfolg (alle 16 Schritte grün)

1. Vault-Plan-Datei (`C:\Brain-Bug\projects\pb-studio\wiki\synthesis\<schnitt-redesign-plan>.md`) bekommt neue Section:

   ```markdown
   ## Live-Verifikation 2026-05-09 — Phase 12.3

   - [x] Schritt 1 — Projekt anlegen
   - [x] Schritt 2 — Audio Import + Analyse
   - ...
   - [x] Schritt 16 — Undo

   Status: alle 16 Schritte grün. Phase 12.3 abgeschlossen.
   ```

2. Screenshots ablegen unter:
   `C:\Brain-Bug\projects\pb-studio\screenshots\schnitt-verify-2026-05-09\`
   (mind. 1 Screenshot pro Schritt 5/6/7/9/10/11/13/14)

3. **User** setzt Vault-Plan-Status auf `status: fixed`. (Nicht Agent.)

4. Repo-Commit (leer, nur Doku-Marker):

   ```bash
   git commit --allow-empty -m "chore(schnitt): live verification 2026-05-09 (all 16 steps)"
   ```

### Fehlschlag (mind. ein Schritt fehlerhaft)

Pro fehlgeschlagenem Schritt:

1. Neuer Bug-File: `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-XXX-schnitt-verify-step-NN.md`
2. YAML-Frontmatter:

   ```yaml
   ---
   id: B-XXX
   title: Schnitt-Verify Schritt NN — <Kurzbeschreibung>
   status: open
   severity: high|medium|low
   discovered: 2026-05-09
   plan: 2026-05-09-schnitt-workspace-redesign
   phase: 12.3
   step: NN
   ---
   ```

3. Body: Erwartung vs. tatsächliches Verhalten, Screenshot-Pfad, Repro-Steps.
4. `log.md` Eintrag mit Datum + Bug-Referenz.
5. `index.md > Aktiver Handoff` aktualisieren.
6. Phase 12 bleibt **offen** bis Bugs gefixt + Re-Verify.

---

## Vault-Pflicht (jeder Sub-Schritt)

Nach jedem Schritt der Klickfolge:

- Living-Plan: Status-Tabelle pro Schritt fortschreiben.
- Bei Bug-Findings: Bug-File **sofort** anlegen, nicht am Ende sammeln.
- `log.md` mit datiertem Eintrag pro namhaftem Befund.
- `index.md > Aktiver Handoff` aktuell halten.

---

## Abschluss

Wenn alle 16 Schritte grün **und** User hat Vault-Plan auf `status: fixed` gesetzt:

- `index.md > Aktiver Handoff` Eintrag „2026-05-09 SCHNITT Workspace Redesign" → Suffix „abgeschlossen 2026-05-09" oder Verschiebung nach „Cornerstones".
- Repo-Spec-Status (`docs/superpowers/specs/2026-05-09-schnitt-workspace-redesign.md`) `draft-approved-for-planning` → `done`.
- `log.md` finaler Eintrag.

Plan-Dateien bleiben archiviert in `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/`.
