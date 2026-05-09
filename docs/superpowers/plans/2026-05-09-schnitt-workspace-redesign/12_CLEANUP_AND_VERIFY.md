# Phase 12 — Cleanup + Live-Verifikation

**Ziel:** Legacy-Code löschen, manuelle Live-Verifikation mit Test-Datensatz, Vault- und Repo-Synthese auf Endstand bringen.

---

## Task 12.1: Tot-Code entfernen — `btn_toggle_inspector`

**Files:**
- Modify: `ui/controllers/workspace_setup.py:620-626` (`_toggle_inspector`)
- Modify: `ui/workspaces/edit_workspace.py:168-174` (Legacy-Visibility-Stub)

- [ ] **Step 1: Methode + Wiring entfernen**

In `workspace_setup.py`:

```python
# Entferne _toggle_inspector komplett.
# Entferne in _create_workspaces:
self.window.btn_toggle_inspector.clicked.connect(self._toggle_inspector)
```

In `edit_workspace.py`: `btn_toggle_inspector`-Erstellung entfernen.

- [ ] **Step 2: Smoke-Run**: App starten, SCHNITT öffnen, Editor-State sehen — Inspector ist permanent rechts sichtbar.

- [ ] **Step 3: Commit**

```bash
git add ui/controllers/workspace_setup.py ui/workspaces/edit_workspace.py
git commit -m "refactor(schnitt): remove dead btn_toggle_inspector code"
```

- [ ] **Step 4: Vault-Update.**

---

## Task 12.2: Alten `EditWorkspace` löschen oder Stub-only halten

**Status 2026-05-09: VERSCHOBEN auf Folge-Plan.** Begründung siehe unten.

**Bewertung (Phase-12-Implementer, 2026-05-09):**

`ui/workspaces/edit_workspace.py` (`EditWorkspace`-Klasse) ist nach Phase 10 noch der hidden Host für 12 Widgets, die Controller- und Setup-Logik direkt greift:

- `ui/controllers/workspace_setup.py:282-335` — 12 Promotionen via `self.window._edit_ws.<attr>` (btn_preview_play, btn_preview_stop, preview_time_label, audio_combo, video_combo, energy_reactivity_slider/spin, btn_generate, btn_auto_edit, keyframe_text, btn_keyframe_string, btn_thumbs_up/down, style_preset_combo).
- `ui/controllers/edit_workspace.py:561,571,572,574` — 4 Direktzugriffe (style_preset_combo, cut_rate_combo, energy_reactivity_slider, breakdown_combo).
- `ui/workspaces/__init__.py` — Re-Export `EditWorkspace`.

Eine saubere Löschung erfordert:

1. Alle 12 Widgets in die jeweiligen `SchnittTab*`-Komponenten migrieren (oder stabile Pass-Through-Properties in SchnittWorkspace bauen).
2. Controller-Split in `ui/controllers/schnitt_actions.py` + `ui/controllers/schnitt_workers.py`.
3. Re-Export aus `ui/workspaces/__init__.py` und `ui/controllers/__init__.py` aktualisieren.
4. main.py-Smoke + Tests in `tests/ui/test_controllers_smoke.py`, `tests/ui/test_cuts_worker_progress.py`, `tests/test_services/test_cycle7_ui_batch.py` an neue Class-Namen anpassen.

Berührt mehr als 3 Files, deutlich >100 Zeilen, hohes Regressions-Risiko (Auto-Edit / Generate-Worker-Pfade). Liegt damit klar außerhalb des Phase-12-Scope „Cleanup + Verify".

**Aktion:** Phase 12.2 wird **nicht** in dieser Phase ausgeführt. Wird in einem eigenen Folge-Plan (Arbeitstitel: „SCHNITT EditWorkspace Sunset") nach erfolgreicher Live-Verifikation behandelt. Tot-Code-Entfernung in 12.1 reicht für den Phase-12-Scope.

---

## Task 12.3: Live-Verifikation mit Test-Datensatz

Test-Datensatz (aus Memory):

- Video-Ordner: `C:\Users\David Lochmann\Documents\Solo_Natur-20260406T220640Z-3-001\Solo_Natur` (103 Files)
- Audio: `Crusty Progressive Psy Set2.mp3` (149 MB DJ-Mix)

- [ ] **Step 1: PB Studio starten**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" main.py
```

- [ ] **Step 2: Manuelle Klickfolge**

  1. PROJEKT-Tab → Neues Projekt anlegen, Name „Schnitt-Verify-2026-05-09".
  2. MATERIAL & ANALYSE-Tab → Audio-Import: Crusty Progressive Psy Set2.mp3. → BPM/Beats analysieren. → Stems separieren.
  3. Video-Import: Solo_Natur (Folder-Import).
  4. Video-Pipeline starten. Warten bis grün.
  5. SCHNITT-Tab öffnen. Erwartung: **Empty State** mit 4 Preset-Buttons.
  6. „Techno"-Button klicken. Erwartung: **Loading State** mit rotierendem Status („Analysiere Audio…" → „Setze Schnitte…" → „Wähle Clips aus…").
  7. Auto-Edit fertig → **Editor State** mit Sub-Tabs „Schnitt" aktiv. Inspector rechts gefüllt.
  8. Im Sub-Tab „Schnitt": auf einen Clip klicken → Inspector zeigt Details.
  9. Auf das Lock-Icon eines Clips klicken → Goldrand erscheint, Schloss füllt.
  10. Sub-Tab „Pacing & Anker" → Reactivity auf 80 → Cut-Rate auf 2 Beats → „Mit neuen Pacing-Einstellungen generieren" klicken. Erwartung: **QMessageBox** „Achtung: Dies überschreibt aktuelle ungelockte Schnitte. Fortfahren?".
  11. „Yes" → erneut Loading, dann Editor. Gesperrter Clip aus Schritt 9 muss noch da sein, ungesperrte Clips wurden ersetzt.
  12. Sub-Tab „Audio" → Waveform sichtbar, Stems-Mixer + LUFS + Tonart befüllt.
  13. Sub-Tab „RL & Notes" → in Notes-Editor schreiben „Test 2026-05-09 Schnitt-Verify". 1 s warten — Footer-Label zeigt „Zuletzt gespeichert: HH:MM:SS".
  14. App schließen, neu öffnen, Projekt laden, SCHNITT → Sub-Tab „RL & Notes" — Notes-Inhalt erscheint wie gespeichert.
  15. Mit der Maus über `cut_rate_combo` scrollen ohne zu klicken. Wert darf sich **nicht** ändern.
  16. Strg+Z drücken. Letzte Aktion (z.B. Lock-Toggle) wird rückgängig gemacht.

- [ ] **Step 3: Befunde dokumentieren**

Vault-Plan-Datei: neue Section „Live-Verifikation 2026-05-09" mit Schritt-Ergebnissen + Screenshots (in `C:\Brain-Bug\projects\pb-studio\screenshots\schnitt-verify-2026-05-09\`).

Bei jedem Schritt der **fehlschlägt**: neuen Bug-File anlegen unter `C:\Brain-Bug\projects\pb-studio\wiki\bugs\B-XXX-*.md` mit YAML-Frontmatter.

- [ ] **Step 4: Bei Erfolg**

User setzt Vault-Plan-Status auf `status: fixed` (NICHT Agent).

- [ ] **Step 5: Commit der finalen Verify-Doku**

```bash
git commit --allow-empty -m "chore(schnitt): live verification 2026-05-09 (all 16 steps)"
```

- [ ] **Step 6: Vault-Update letztes Mal**: Status-Tabelle auf „abgeschlossen", Living Document setzt User auf `fixed`.

---

## Plan-Abschluss

Wenn Phase 12 fertig + User hat Vault-Plan auf `fixed` gesetzt:

- `index.md > Aktiver Handoff` Eintrag „2026-05-09 SCHNITT Workspace Redesign" → bekommt Suffix „abgeschlossen 2026-05-09" oder wandert nach unten in „Cornerstones".
- Repo-Spec Status `draft-approved-for-planning` → `done`.
- `log.md` finale Eintragung.

Plan-Dateien bleiben als Artefakt in `docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/` archiviert.
