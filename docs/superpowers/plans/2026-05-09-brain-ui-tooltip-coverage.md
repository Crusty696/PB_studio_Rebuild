# Brain UI Tooltip Coverage Implementation Plan

> **⛔ SUPERSEDED 2026-07-16 — PLAN GESCHLOSSEN.** Bucket-7-Aufloesung: die Brain-UI wurde
> spaeter zu `ui/studio_brain/`-Tabs umgebaut (haben bereits Tooltips). Rest-Arbeit (Tooltips
> fuer die noch-live Alt-Widgets `brain_v3_feedback_popup`/`brain_v3_learning_dialog`,
> 0 setToolTip) → `PB-STUDIO-MASTER-OFFENE-TASKS-2026-07-16` Bucket 4 (Agent-frei, low-prio),
> Decision D-071. Nicht mehr als aktiver Plan nutzen.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vollständige Tooltip-Coverage aller interaktiven Bedienelemente in den Brain-V3-Widgets (Feedback-Popup, Stats-Panel, Learning-Dialog) plus Brain-v2-Tab und studio_brain_window-Brain-v2-Tab. Jeder Tooltip erklärt **WAS** das Element macht, **WIE** es benutzt wird und **WANN** es relevant ist. Hotkey-Mapping (Hotkeys 1-4) wird zusätzlich per Docstring im Code dokumentiert.

**Architecture:** Reine UI-Polish-Aufgabe. Keine Logik-Änderungen. Pro Widget wird nach `setText`/`addWidget` ein `setToolTip(...)`-Aufruf eingefügt. Bestehende Tests in `tests/test_services/test_brain_v3_phase5_widgets.py` werden um Tooltip-Assertions erweitert (TDD: Test failt → setToolTip einbauen → grün → commit). `setStatusTip` wird **nicht** verwendet (kein StatusBar im Brain-Window). Brain-v2-Tab-Tooltip in `studio_brain_window.py` ist try/except-geschützt, weil der Tab nur bei `PB_STUDIO_BRAIN_V2=1` existiert (Z.259).

**Tech Stack:** PySide6 6.x (`QWidget.setToolTip(str)`, `QTabWidget.setTabToolTip(int, str)`), pytest mit `QApplication`-Module-Fixture (siehe `test_brain_v3_phase5_widgets.py:25-28`).

**Verifikations-Doktrin (CLAUDE.md TOP RULE):** Jede Änderung wird vor dem Commit über pytest live gegen GTX 1060 verifiziert. Keine Annahmen — Datei-Zeilen werden vor jedem Edit per `Read` erneut geprüft (Code-Drift möglich). Bei Konflikt mit dem Plan: stop + ask.

**Vault-Sync:** Pro Tier (1, 2, 3) eine Vault-Eintrag in `C:\Brain-Bug\projects\pb-studio\`. Nicht pro Sub-Task — bündeln. **User-Ausnahme 2026-05-13 / Vault-Decision D-043:** Diese Bündelung ist für diesen Tooltip-Plan explizit erlaubt und überschreibt hier die sonstige D-042/AGENTS-Per-Sub-Step-Regel. Code/Test-Arbeit bleibt taskweise, TDD + Verifikation bleiben Pflicht.

---

## File Structure

| Datei | Verantwortung | Änderung |
|-------|---------------|----------|
| `ui/widgets/brain_v3_feedback_popup.py` | 4-Klick-Bewertung mit Hotkeys 1-4 | Tooltip pro Button + Cancel-Button + Docstring `_wire_hotkeys()` |
| `ui/widgets/brain_v3_stats_panel.py` | Lernstatus + Reset (two-step) | Tooltip auf Reset, Refresh, ProgressBar, beide Trees, beide Labels |
| `ui/widgets/brain_v3_learning_dialog.py` | Lern-Session-Dialog mit 15 Stichproben | Tooltip auf Liste, Preview-Play/Stop, Bewerten, Schliessen, Status-Label |
| `ui/studio_brain_window.py` | Brain-Window-Tabs (V1/V2) | `setTabToolTip(6, ...)` für Brain-v2-Tab, try/except (Tab existiert nur bei Env-Var) |
| `ui/studio_brain/brain_v2_tab.py` | Brain-v2-Status-Tab | Tooltip auf Refresh-Button |
| `tests/test_services/test_brain_v3_phase5_widgets.py` | Phase-5-Widget-Tests | 5 neue Tooltip-Assertions (1 pro Widget-Datei + 1 Hotkey-Docstring-Test) |

---

## Reihenfolge & Risiko

Plan folgt der vom User vorgegebenen Reihenfolge:

1. **Task 1** — Feedback-Popup-Buttons (Tier 1, **höchstes Risiko**: User-Verwirrung über Hotkey-Wirkung)
2. **Task 2** — Stats-Panel Reset-Button (Tier 1, **Daten-Verlust-Risiko**: destruktive Aktion ohne Tooltip-Warnung)
3. **Task 3** — Stats-Panel ProgressBar + restliche Widgets (Tier 1)
4. **Task 4** — Learning-Dialog ListWidget + Status-Label (Tier 2)
5. **Task 5** — Learning-Dialog Preview/Aktions-Buttons (Tier 2)
6. **Task 6** — studio_brain_window.py Brain-v2-Tab-Tooltip (Tier 2)
7. **Task 7** — Hotkey-Mapping-Docstring in `_wire_hotkeys()` (Tier 3)
8. **Task 8** — Brain-v2-Tab Refresh-Button (Tier 3)
9. **Task 9** — Vault-Synthesis + finaler Pytest-Lauf

Heikle Bereiche:
- **Task 2 (Reset)**: Tooltip-Text muss mit dem QMessageBox-Text aus Z.181-185 konsistent sein — sonst widerspricht UI sich. Reset-Wirkung (`axis_weights + pattern_correlations` löschen, Embedding-Cache **bleibt**) ist plan-doc-relevant (`06_PHASES.md` Phase 3 + 5).
- **Task 6 (Brain-v2-Tab)**: Tab-Index 6 existiert **nur bei** `PB_STUDIO_BRAIN_V2=1`. `setTabToolTip` mit ungültigem Index wirft keine Exception (Qt ignoriert), aber sauberer ist try/except-Block am bestehenden Konstruktions-Block.
- **Task 1 (Hotkeys)**: Hotkeys 1-4 sind in `_wire_hotkeys()` Z.100-104 codiert. Tooltip muss exakt das `alpha`/`beta`-Delta nennen, das im Modul-Docstring Z.4-7 steht.

---

## Tooltip-Standard

Pro Tooltip:
- Sprache **Deutsch** (Konsistenz mit `studio_brain_window.py:283-318`).
- Länge 50-150 Zeichen.
- Pattern: `<WAS>. <WIE / WANN>. <WARNUNG bei destruktiv>.`
- Hotkeys: `(Hotkey: <Taste>)` am Ende.
- Destruktive Aktionen: `Achtung: ...` Prefix.

---

## Task 1 — Feedback-Popup-Buttons (Tier 1)

**Files:**
- Modify: `ui/widgets/brain_v3_feedback_popup.py:84-91` (Button-Loop) + `:95-96` (Cancel-Button)
- Test: `tests/test_services/test_brain_v3_phase5_widgets.py` (neue Test-Funktion ergänzen)

**Vorbedingung:** Datei vor Edit re-lesen (Z.37-43 enthalten `FEEDBACK_BUTTONS`-Konstante — wird mutmaßlich um Tooltip-Spalte erweitert; vor Edit verifizieren ob Konstante anderweitig benutzt wird, sonst Tooltip-Map separat halten).

- [ ] **Step 1.1: Re-Read Source-Datei + Konstanten-Nutzung prüfen**

```bash
grep -rn "FEEDBACK_BUTTONS" "C:/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/" --include="*.py"
```
Expected: nur `brain_v3_feedback_popup.py` selbst + `test_brain_v3_phase5_widgets.py:80` (Import des Symbols). Keine externen Mutationen — sicher zu modifizieren.

Falls externe Nutzung gefunden: STOP. Tooltip-Map separat (neue Konstante `FEEDBACK_TOOLTIPS`) statt Tuple zu erweitern.

- [ ] **Step 1.2: Failing Test schreiben** (am Ende von `tests/test_services/test_brain_v3_phase5_widgets.py` einfügen)

```python
def test_feedback_popup_buttons_have_tooltips(qt_app, isolated_appdata):
    """Tier-1: Jeder Bewertungs-Button + Cancel-Button hat einen
    aussagekraeftigen Tooltip mit Hotkey-Hinweis."""
    from ui.widgets.brain_v3_feedback_popup import (
        BrainV3FeedbackPopup,
        FEEDBACK_BUTTONS,
    )
    from PySide6.QtWidgets import QPushButton
    svc = BrainV3Service()
    popup = BrainV3FeedbackPopup(cut_id=1, service=svc, context=CutContext())
    btns = popup.findChildren(QPushButton)
    # 4 Bewertungs-Buttons + 1 Abbrechen
    assert len(btns) == 5
    rating_keys = {r for r, _, _ in FEEDBACK_BUTTONS}
    for btn in btns:
        tip = btn.toolTip()
        assert tip, f"Button '{btn.text()}' ohne Tooltip"
        assert len(tip) >= 50, f"Tooltip zu kurz: {tip!r}"
        # Hotkey-Hinweis pro Bewertungs-Button
        if any(rk in btn.text().lower() or btn.text().startswith(num)
               for rk in rating_keys for num in "1234"):
            assert "Hotkey" in tip or "alpha" in tip or "beta" in tip
    popup.deleteLater()
```

- [ ] **Step 1.3: Test laufen lassen — muss FAILEN**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_feedback_popup_buttons_have_tooltips -v --tb=short
```
Expected: FAIL — `assert tip, "Button ... ohne Tooltip"`

- [ ] **Step 1.4: Tooltip-Map als Konstante einführen**

In `ui/widgets/brain_v3_feedback_popup.py` direkt nach `FEEDBACK_BUTTONS` (Z.43):

```python
# Tooltip-Texte pro Rating (Tier-1 Coverage 2026-05-09)
FEEDBACK_TOOLTIPS: dict[str, str] = {
    "perfect":   "Beste Bewertung. Cut passt perfekt zur Musik. "
                 "Erhoeht alpha um +2.0 (Brain V3 lernt: dieser Kontext liefert "
                 "perfekte Cuts). (Hotkey: 1)",
    "fits":      "Cut passt gut, aber nicht perfekt. "
                 "Erhoeht alpha um +1.0 (positives Feedback, mittlere Staerke). "
                 "(Hotkey: 2)",
    "not_quite": "Cut passt nicht ganz. "
                 "Erhoeht beta um +1.0 (negatives Feedback, mittlere Staerke). "
                 "(Hotkey: 3)",
    "no_match":  "Cut passt gar nicht zur Musik. "
                 "Erhoeht beta um +2.0 (Brain V3 lernt: dieser Kontext liefert "
                 "schlechte Cuts). (Hotkey: 4)",
}
```

- [ ] **Step 1.5: Button-Loop um setToolTip ergänzen** (Z.84-91 → erweitert)

```python
        for rating, label, style in FEEDBACK_BUTTONS:
            btn = QPushButton(label)
            btn.setStyleSheet(
                style
                + " padding: 6px 10px; border-radius: 4px; font-weight: 600;"
            )
            btn.setToolTip(FEEDBACK_TOOLTIPS[rating])
            btn.clicked.connect(lambda _checked=False, r=rating: self._submit(r))
            root.addWidget(btn)
```

- [ ] **Step 1.6: Cancel-Button-Tooltip ergänzen** (Z.95-96 → erweitert)

```python
        cancel = QPushButton("Abbrechen (Esc)")
        cancel.setToolTip(
            "Schliesst den Dialog ohne Bewertung. Kein Feedback an Brain V3. "
            "(Hotkey: Esc)"
        )
        cancel.clicked.connect(self.reject)
```

- [ ] **Step 1.7: Test erneut laufen — muss PASSEN**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_feedback_popup_buttons_have_tooltips -v --tb=short
```
Expected: PASS

- [ ] **Step 1.8: Regression-Check** (alle Phase-5-Widget-Tests)

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py -v --tb=short
```
Expected: alle gruen (mind. 7+ Tests).

- [ ] **Step 1.9: Commit**

```bash
git add ui/widgets/brain_v3_feedback_popup.py tests/test_services/test_brain_v3_phase5_widgets.py
git commit -m "feat(brain-v3-ui): tooltips fuer Feedback-Popup-Buttons (Tier 1)

- 4 Bewertungs-Buttons (perfect/fits/not_quite/no_match) erklaeren
  alpha/beta-Delta + Hotkey 1-4
- Cancel-Button erklaert Esc + 'kein Feedback'
- FEEDBACK_TOOLTIPS-Konstante als Single-Source-of-Truth
- Test test_feedback_popup_buttons_have_tooltips erzwingt Coverage"
```

---

## Task 2 — Stats-Panel Reset-Button (Tier 1, destruktiv)

**Files:**
- Modify: `ui/widgets/brain_v3_stats_panel.py:113-119`
- Test: erweitere `test_brain_v3_phase5_widgets.py`

**Vorbedingung:** Re-Read Z.113-119 + Z.181-186 (QMessageBox-Text). Tooltip-Inhalt muss mit der Confirmation-Message konsistent sein.

- [ ] **Step 2.1: Re-Read + Konsistenz-Check**

Read `ui/widgets/brain_v3_stats_panel.py:113-202`. Bestätige:
- Reset-Button Z.113 ruft `_on_reset_clicked` Z.166
- QMessageBox.warning Z.178 zeigt Text "Das loescht alle gelernten Gewichte (axis_weights + pattern_correlations). Embedding-Cache bleibt erhalten."
- Tooltip muss diese Aussage spiegeln (gleiche Tabellen-Namen).

- [ ] **Step 2.2: Failing Test**

```python
def test_stats_panel_reset_button_has_destructive_tooltip(qt_app, isolated_appdata):
    """Tier-1: Reset-Button (destruktiv) hat Warnung + Erklaerung im Tooltip."""
    from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel
    svc = BrainV3Service()
    panel = BrainV3StatsPanel(service=svc, auto_refresh_ms=10_000)
    tip = panel._btn_reset.toolTip()
    assert tip, "Reset-Button ohne Tooltip"
    assert len(tip) >= 80, f"Tooltip zu kurz: {tip!r}"
    # Warnung muss klar sein
    assert "Achtung" in tip or "destruktiv" in tip.lower() or "loescht" in tip.lower()
    # Konsistenz mit QMessageBox-Text
    assert "axis_weights" in tip
    assert "Embedding-Cache" in tip
    panel.deleteLater()
```

- [ ] **Step 2.3: Test FAILEN sehen**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_stats_panel_reset_button_has_destructive_tooltip -v --tb=short
```
Expected: FAIL.

- [ ] **Step 2.4: setToolTip auf Reset-Button** (Z.113-119 → erweitert)

```python
        self._btn_reset = QPushButton("Reset Hirn-Store")
        self._btn_reset.setStyleSheet(
            "QPushButton { background: #6e1f1f; color: white; padding: 4px 10px; }"
            "QPushButton:hover { background: #8a2828; }"
        )
        self._btn_reset.setToolTip(
            "Achtung: loescht alle gelernten Gewichte "
            "(axis_weights + pattern_correlations). "
            "Embedding-Cache bleibt erhalten. "
            "Erfordert eine zweistufige Bestaetigung (Token + Yes/Cancel-Dialog). "
            "Nach dem Reset startet Brain V3 wieder im Cold-Start."
        )
        self._btn_reset.clicked.connect(self._on_reset_clicked)
```

- [ ] **Step 2.5: Test PASSEN sehen**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_stats_panel_reset_button_has_destructive_tooltip -v --tb=short
```
Expected: PASS.

- [ ] **Step 2.6: Commit**

```bash
git add ui/widgets/brain_v3_stats_panel.py tests/test_services/test_brain_v3_phase5_widgets.py
git commit -m "feat(brain-v3-ui): destruktive Tooltip-Warnung auf Reset-Hirn-Store-Button

- Erklaert WAS geloescht wird (axis_weights + pattern_correlations)
- Erklaert WAS bleibt (Embedding-Cache)
- Erklaert die Two-Step-Confirmation
- Erklaert Cold-Start nach Reset"
```

---

## Task 3 — Stats-Panel restliche Widgets (Tier 1)

**Files:**
- Modify: `ui/widgets/brain_v3_stats_panel.py:72-89` (Labels + ProgressBar) + `:99-106` (Trees) + `:110-112` (Refresh)
- Test: erweitere `test_brain_v3_phase5_widgets.py`

- [ ] **Step 3.1: Re-Read Z.62-130**

Bestätige Widget-Liste:
- `_lbl_total_clicks` Z.72
- `_lbl_learned` Z.77 + `_bar_learned` Z.78-83
- `_lbl_last` Z.87
- `_tree_pos` Z.100
- `_tree_neg` Z.105
- `_btn_refresh` Z.110

- [ ] **Step 3.2: Failing Test**

```python
def test_stats_panel_widgets_have_tooltips(qt_app, isolated_appdata):
    """Tier-1: Alle interaktiven + status-anzeigenden Widgets im Stats-Panel
    haben aussagekraeftige Tooltips."""
    from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel
    svc = BrainV3Service()
    panel = BrainV3StatsPanel(service=svc, auto_refresh_ms=10_000)

    # ProgressBar erklaert die 17 Achsen
    pb_tip = panel._bar_learned.toolTip()
    assert pb_tip and "17" in pb_tip and "Achsen" in pb_tip
    assert len(pb_tip) >= 80

    # Refresh
    rf_tip = panel._btn_refresh.toolTip()
    assert rf_tip and len(rf_tip) >= 30

    # Trees (Top 5 positive / negative)
    pos_tip = panel._tree_pos.toolTip()
    neg_tip = panel._tree_neg.toolTip()
    assert pos_tip and "alpha" in pos_tip.lower()
    assert neg_tip and "beta" in neg_tip.lower()

    # Total-Klicks-Label + Learned-Label + Last-Feedback-Label
    assert panel._lbl_total_clicks.toolTip()
    assert panel._lbl_learned.toolTip()
    assert panel._lbl_last.toolTip()
    panel.deleteLater()
```

- [ ] **Step 3.3: Test FAILEN sehen**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_stats_panel_widgets_have_tooltips -v --tb=short
```
Expected: FAIL.

- [ ] **Step 3.4: Tooltips einfügen** (Z.72-112 erweitern)

```python
        # Total Klicks
        self._lbl_total_clicks = QLabel("Total Klicks: —")
        self._lbl_total_clicks.setToolTip(
            "Summe aller bisherigen Cut-Bewertungen. Jeder 4-Klick-Feedback "
            "(Hotkeys 1-4) zaehlt als ein Klick. Mehr Klicks = mehr Lerndaten "
            "fuer Brain V3."
        )
        root.addWidget(self._lbl_total_clicks)

        # Cold/Learned
        learned_row = QHBoxLayout()
        self._lbl_learned = QLabel("Gelernte Achsen: —/17")
        self._lbl_learned.setToolTip(
            "Brain V3 lernt entlang 17 Achsen (10 Audio + 7 Video). "
            "Eine Achse gilt als 'gelernt', wenn mindestens 10 Beobachtungen "
            "(MIN_CONFIDENT_SAMPLES) im konfidentesten Bucket vorliegen. "
            "Rest = Cold-Start (Heuristik aus TriggerSettings)."
        )
        self._bar_learned = QProgressBar()
        self._bar_learned.setRange(0, 17)
        self._bar_learned.setFormat("%v / 17")
        self._bar_learned.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._bar_learned.setToolTip(
            "Visualisiert wie viele der 17 Brain-V3-Achsen aus echten "
            "Lerndaten kommen (vs. Cold-Start-Defaults). "
            "Voll = Brain V3 ist auf alle Achsen kalibriert."
        )
        learned_row.addWidget(self._lbl_learned, 1)
        learned_row.addWidget(self._bar_learned, 2)
        root.addLayout(learned_row)

        # Last feedback at
        self._lbl_last = QLabel("Letztes Feedback: nie")
        self._lbl_last.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        self._lbl_last.setToolTip(
            "Zeitstempel des letzten 4-Klick-Feedbacks. "
            "'nie' = noch keine Bewertung in diesem Projekt."
        )
        root.addWidget(self._lbl_last)
```

Trees (Z.99-106):

```python
        # Top positive
        root.addWidget(QLabel("Top 5 positive Buckets:"))
        self._tree_pos = self._make_bucket_tree()
        self._tree_pos.setToolTip(
            "Die 5 staerksten positiv gelernten Kontext-Buckets "
            "(hoechstes alpha/beta-Verhaeltnis). "
            "Jede Zeile: Achse + Backoff-Level + Context-Key + alpha + beta. "
            "Diese Buckets boostet Brain V3 beim Reranking."
        )
        root.addWidget(self._tree_pos)

        # Top negative
        root.addWidget(QLabel("Top 5 negative Buckets:"))
        self._tree_neg = self._make_bucket_tree()
        self._tree_neg.setToolTip(
            "Die 5 staerksten negativ gelernten Kontext-Buckets "
            "(niedrigstes alpha/beta-Verhaeltnis). "
            "Jede Zeile: Achse + Backoff-Level + Context-Key + alpha + beta. "
            "Diese Buckets dimmt Brain V3 beim Reranking."
        )
        root.addWidget(self._tree_neg)
```

Refresh (Z.110-112):

```python
        self._btn_refresh = QPushButton("Refresh")
        self._btn_refresh.setToolTip(
            "Holt die aktuellen Statistiken vom BrainV3Service. "
            "Auto-Refresh alle 5s ist aktiv — Klick fuer sofortiges Update."
        )
        self._btn_refresh.clicked.connect(self.refresh)
```

- [ ] **Step 3.5: Test PASSEN sehen**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_stats_panel_widgets_have_tooltips -v --tb=short
```
Expected: PASS.

- [ ] **Step 3.6: Regression-Check + Commit**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py -v --tb=short
git add ui/widgets/brain_v3_stats_panel.py tests/test_services/test_brain_v3_phase5_widgets.py
git commit -m "feat(brain-v3-ui): tooltips fuer Stats-Panel-Widgets (Tier 1 abgeschlossen)

- ProgressBar erklaert 17 Achsen + MIN_CONFIDENT_SAMPLES=10
- Top-Positive/Negative-Trees erklaeren alpha/beta-Verhaeltnis
- Total-Klicks/Learned/Last-Feedback-Labels erklaert
- Refresh-Button erklaert Auto-Refresh + Manual-Trigger"
```

---

## Task 4 — Learning-Dialog ListWidget + Status (Tier 2)

**Files:**
- Modify: `ui/widgets/brain_v3_learning_dialog.py:77-87` (Status-Label + List)
- Test: erweitere `test_brain_v3_phase5_widgets.py`

- [ ] **Step 4.1: Re-Read Z.68-123**

Bestätige `_list` Z.84 mit `itemDoubleClicked` Z.86. Tooltip muss Doppelklick-Verhalten erklären.

- [ ] **Step 4.2: Failing Test**

```python
def test_learning_dialog_list_has_tooltip(qt_app, isolated_appdata):
    """Tier-2: ListWidget erklaert Doppelklick-Verhalten + Confidence-Faerbung."""
    from ui.widgets.brain_v3_learning_dialog import BrainV3LearningSessionDialog
    svc = BrainV3Service()
    dlg = BrainV3LearningSessionDialog(service=svc, n_samples=5)
    list_tip = dlg._list.toolTip()
    assert list_tip
    assert "Doppelklick" in list_tip
    assert "uncertainty" in list_tip.lower() or "confidence" in list_tip.lower()
    # Status-Label
    assert dlg._lbl_status.toolTip()
    dlg.deleteLater()
```

- [ ] **Step 4.3: Test FAILEN sehen**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_learning_dialog_list_has_tooltip -v --tb=short
```
Expected: FAIL.

- [ ] **Step 4.4: Tooltips einfügen**

`_lbl_status` (Z.77-79):

```python
        self._lbl_status = QLabel("Lade Stichproben ...")
        self._lbl_status.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 11px;")
        self._lbl_status.setToolTip(
            "Status der aktuellen Lern-Session: angefragte vs. geladene "
            "Stichproben + bereits bewertete Cuts."
        )
        root.addWidget(self._lbl_status)
```

`_list` (Z.84-87):

```python
        self._list = QListWidget()
        self._list.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._list.setToolTip(
            "Top-15 unsicherste Cuts nach Bayes-Varianz. "
            "Doppelklick auf einen Eintrag oeffnet das Feedback-Popup. "
            "Hintergrundfarbe = Confidence (rot=unsicher, gruen=sicher). "
            "Bewertete Cuts werden aus der Liste entfernt."
        )
        self._list.itemDoubleClicked.connect(self._on_item_activated)
        self._list.currentItemChanged.connect(self._on_current_item_changed)
        body.addWidget(self._list, 1)
```

- [ ] **Step 4.5: Test PASSEN sehen + Commit**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_learning_dialog_list_has_tooltip -v --tb=short
git add ui/widgets/brain_v3_learning_dialog.py tests/test_services/test_brain_v3_phase5_widgets.py
git commit -m "feat(brain-v3-ui): tooltips fuer Learning-Dialog Liste + Status (Tier 2)

- ListWidget erklaert Doppelklick-Aktion + Confidence-Faerbung
- Status-Label erklaert Stichproben/Bewertet/Verbleibend"
```

---

## Task 5 — Learning-Dialog Preview/Action-Buttons (Tier 2)

**Files:**
- Modify: `ui/widgets/brain_v3_learning_dialog.py:92-122` (Preview-Label + Buttons + Aktionen)
- Test: erweitere `test_brain_v3_phase5_widgets.py`

- [ ] **Step 5.1: Re-Read Z.90-123**

Bestätige Buttons:
- `_btn_preview_play` Z.101 — Toggle Play/Pause
- `_btn_preview_stop` Z.105 — Stop
- `_btn_open` Z.116 "Bewerten"
- `_btn_close` Z.120 "Schliessen"

- [ ] **Step 5.2: Failing Test**

```python
def test_learning_dialog_action_buttons_have_tooltips(qt_app, isolated_appdata):
    """Tier-2: Preview-Play/Stop + Bewerten + Schliessen haben Tooltips."""
    from ui.widgets.brain_v3_learning_dialog import BrainV3LearningSessionDialog
    svc = BrainV3Service()
    dlg = BrainV3LearningSessionDialog(service=svc, n_samples=5)
    assert dlg._btn_preview_play.toolTip()
    assert dlg._btn_preview_stop.toolTip()
    assert dlg._btn_open.toolTip()
    assert dlg._btn_close.toolTip()
    assert dlg._lbl_preview.toolTip()
    dlg.deleteLater()
```

- [ ] **Step 5.3: Test FAILEN sehen**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_learning_dialog_action_buttons_have_tooltips -v --tb=short
```
Expected: FAIL.

- [ ] **Step 5.4: Tooltips einfügen**

Preview-Label (Z.92-94):

```python
        self._lbl_preview = QLabel("Preview: keine Stichprobe")
        self._lbl_preview.setStyleSheet("font-weight: 600; font-size: 12px;")
        self._lbl_preview.setToolTip(
            "Zeigt welche Stichprobe gerade im Vorschau-Player liegt. "
            "Wird durch Auswahl eines Listen-Eintrags aktualisiert."
        )
        preview_box.addWidget(self._lbl_preview)
```

Preview-Buttons (Z.101-108):

```python
        self._btn_preview_play = QPushButton("Preview starten")
        self._btn_preview_play.setToolTip(
            "Startet Audio + Video an der gespeicherten Cut-Position. "
            "Waehrend der Wiedergabe: Pause-Toggle. "
            "Vor der Bewertung empfohlen, damit du den Kontext kennst."
        )
        self._btn_preview_play.clicked.connect(self._toggle_preview)
        self._btn_preview_play.setEnabled(False)
        preview_actions.addWidget(self._btn_preview_play)

        self._btn_preview_stop = QPushButton("Stop")
        self._btn_preview_stop.setToolTip(
            "Stoppt Audio + Video sofort. Setzt den Player zurueck."
        )
        self._btn_preview_stop.clicked.connect(self._stop_preview)
        self._btn_preview_stop.setEnabled(False)
        preview_actions.addWidget(self._btn_preview_stop)
```

Action-Buttons (Z.116-122):

```python
        self._btn_open = QPushButton("Bewerten")
        self._btn_open.setToolTip(
            "Oeffnet das 4-Klick-Feedback-Popup fuer den ausgewaehlten Cut. "
            "Alternative zum Doppelklick in der Liste."
        )
        self._btn_open.clicked.connect(self._on_open_clicked)
        actions.addWidget(self._btn_open)
        actions.addStretch(1)

        self._btn_close = QPushButton("Schliessen")
        self._btn_close.setToolTip(
            "Beendet die Lern-Session. Bereits abgegebene Bewertungen sind "
            "gespeichert. Verbleibende Cuts werden nicht weiter gefragt."
        )
        self._btn_close.clicked.connect(self._on_close_clicked)
        actions.addWidget(self._btn_close)
        root.addLayout(actions)
```

- [ ] **Step 5.5: Test PASSEN + Commit**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_learning_dialog_action_buttons_have_tooltips -v --tb=short
git add ui/widgets/brain_v3_learning_dialog.py tests/test_services/test_brain_v3_phase5_widgets.py
git commit -m "feat(brain-v3-ui): tooltips fuer Learning-Dialog Preview + Action-Buttons (Tier 2 abgeschlossen)

- Preview-Play (Toggle Pause) + Stop + Bewerten + Schliessen erklaert
- Preview-Label erklaert die Bindung an Listen-Auswahl"
```

---

## Task 6 — studio_brain_window Brain-v2-Tab-Tooltip (Tier 2)

**Files:**
- Modify: `ui/studio_brain_window.py:259-270` (Brain-v2-Tab-Block + Tooltip-Block)

**Wichtig:** Brain-v2-Tab existiert nur bei `PB_STUDIO_BRAIN_V2=1`. `setTabToolTip` muss innerhalb des try/except-Blocks bzw. nur dann gesetzt werden, wenn der Tab erfolgreich angefügt wurde. Tab-Index ist `self._tabs.indexOf(self._brain_v2_tab)` — robuster als hardcoded 6.

- [ ] **Step 6.1: Re-Read Z.259-270 + Z.282-318**

Bestätige:
- Z.259 `if os.environ.get("PB_STUDIO_BRAIN_V2") == "1":`
- Z.265 `self._tabs.addTab(self._brain_v2_tab, _TAB_LABELS[6])`
- Existing Tooltips Z.283-318 für Tabs 0-5
- `_TAB_LABELS[6]` muss in der Datei prüfbar sein (oben im Modul) — falls nicht, Tooltip-Set vom Tab-Index 6 ablesen

```bash
grep -n "_TAB_LABELS" "C:/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/ui/studio_brain_window.py"
```

- [ ] **Step 6.2: Failing Test** (Env-Var aktivieren!)

```python
def test_studio_brain_window_brain_v2_tab_has_tooltip(qt_app, monkeypatch, isolated_appdata):
    """Tier-2: Brain-v2-Tab (nur via PB_STUDIO_BRAIN_V2=1 sichtbar) hat
    setTabToolTip()."""
    monkeypatch.setenv("PB_STUDIO_BRAIN_V2", "1")
    from ui.studio_brain_window import StudioBrainWindow
    win = StudioBrainWindow()
    assert hasattr(win, "_brain_v2_tab"), "Brain-v2-Tab nicht konstruiert"
    idx = win._tabs.indexOf(win._brain_v2_tab)
    assert idx >= 0
    tip = win._tabs.tabToolTip(idx)
    assert tip and len(tip) >= 50
    win.close()
    win.deleteLater()
```

- [ ] **Step 6.3: Test FAILEN**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_studio_brain_window_brain_v2_tab_has_tooltip -v --tb=short
```
Expected: FAIL (kein Tooltip auf Tab 6).

Falls Test crasht weil StudioBrainWindow andere Hard-Deps hat (BrainService etc.) → Test als skip-when-deps-missing markieren ODER lokal nur bestätigen via interaktiver Inspektion. Fallback siehe Step 6.4b.

- [ ] **Step 6.4: setTabToolTip im Brain-v2-Block einfügen** (Z.259-267 erweitert)

```python
        if os.environ.get("PB_STUDIO_BRAIN_V2") == "1":
            try:
                session_factory = getattr(self._brain_service, "session_factory", None)
                if session_factory is None:
                    session_factory = getattr(self._brain_service, "_session_factory", None)
                self._brain_v2_tab = BrainV2Tab(session_factory=session_factory, parent=self._tabs)
                self._tabs.addTab(self._brain_v2_tab, _TAB_LABELS[6])
                self._tabs.setTabToolTip(
                    self._tabs.indexOf(self._brain_v2_tab),
                    "Brain v2 (experimentell, via PB_STUDIO_BRAIN_V2=1 aktiviert): "
                    "Read-only Status der Brain-v2-DB. Zeigt Entities, Facts, "
                    "Decisions, Memories, Notes. Refresh holt aktuelle Zaehler.",
                )
            except Exception as exc:
                logger.warning("BrainV2Tab disabled after construction failure: %s", exc)
```

- [ ] **Step 6.4b (Fallback wenn Test in 6.3 crashed):** Falls `StudioBrainWindow()` ohne explizite Service-Mocks nicht konstruierbar ist, Test entweder:
  1. Mit `pytest.importorskip` + Mocks ausstatten (heavy), oder
  2. Test überspringen und stattdessen einen **separaten Static-Code-Test** schreiben:

```python
def test_studio_brain_window_source_contains_brain_v2_tab_tooltip():
    """Static-Source-Test (kein QApp-Boot): Sourcecode enthaelt
    setTabToolTip-Aufruf im Brain-v2-Block."""
    from pathlib import Path
    src = Path(__file__).resolve().parents[2] / "ui" / "studio_brain_window.py"
    text = src.read_text(encoding="utf-8")
    # Brain-v2-Block beginnt mit `if os.environ.get("PB_STUDIO_BRAIN_V2")`
    block_start = text.index('PB_STUDIO_BRAIN_V2')
    block = text[block_start:block_start + 1500]
    assert "setTabToolTip" in block
    assert "Brain v2" in block
```

Entscheidung welche Variante: bei FAIL des dynamischen Tests → Static-Variante als Fallback einbauen. **Vorab nicht entscheiden** — Live-Lauf zeigt es.

- [ ] **Step 6.5: Test PASSEN + Commit**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py -k "brain_v2_tab" -v --tb=short
git add ui/studio_brain_window.py tests/test_services/test_brain_v3_phase5_widgets.py
git commit -m "feat(brain-ui): setTabToolTip fuer Brain-v2-Tab (Tier 2)

- Brain-v2-Tab existiert nur bei PB_STUDIO_BRAIN_V2=1
- Tooltip erklaert Env-Var-Gate + Read-only-Inhalt
- Tab-Index dynamisch via indexOf() (kein hardcoded 6)"
```

---

## Task 7 — Hotkey-Mapping-Docstring (Tier 3)

**Files:**
- Modify: `ui/widgets/brain_v3_feedback_popup.py:100-104` (`_wire_hotkeys`-Methode)

- [ ] **Step 7.1: Re-Read Z.100-104**

```python
    def _wire_hotkeys(self) -> None:
        # Hotkey 1-4 -> sofort senden
        for idx, (rating, _label, _style) in enumerate(FEEDBACK_BUTTONS, start=1):
            sc = QShortcut(QKeySequence(str(idx)), self)
            sc.activated.connect(lambda r=rating: self._submit(r))
```

- [ ] **Step 7.2: Failing Test**

```python
def test_feedback_popup_wire_hotkeys_has_docstring():
    """Tier-3: _wire_hotkeys() enthaelt eine Docstring mit Mapping 1-4."""
    from ui.widgets.brain_v3_feedback_popup import BrainV3FeedbackPopup
    doc = BrainV3FeedbackPopup._wire_hotkeys.__doc__ or ""
    assert "1" in doc and "2" in doc and "3" in doc and "4" in doc
    assert "perfect" in doc and "no_match" in doc
    assert len(doc) >= 100
```

- [ ] **Step 7.3: Test FAILEN**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_feedback_popup_wire_hotkeys_has_docstring -v --tb=short
```
Expected: FAIL.

- [ ] **Step 7.4: Docstring einfügen**

```python
    def _wire_hotkeys(self) -> None:
        """Hotkeys 1-4 -> sofort feedback() senden, 1:1-Mapping zu FEEDBACK_BUTTONS.

        Mapping (Plan-Doc 06_PHASES.md Z.414-417):
            Taste 1 -> "perfect"   (alpha += 2.0)
            Taste 2 -> "fits"      (alpha += 1.0)
            Taste 3 -> "not_quite" (beta  += 1.0)
            Taste 4 -> "no_match"  (beta  += 2.0)

        Esc schliesst den Dialog ohne Feedback (QDialog-Default).
        """
        for idx, (rating, _label, _style) in enumerate(FEEDBACK_BUTTONS, start=1):
            sc = QShortcut(QKeySequence(str(idx)), self)
            sc.activated.connect(lambda r=rating: self._submit(r))
```

- [ ] **Step 7.5: Test PASSEN + Commit**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_feedback_popup_wire_hotkeys_has_docstring -v --tb=short
git add ui/widgets/brain_v3_feedback_popup.py tests/test_services/test_brain_v3_phase5_widgets.py
git commit -m "docs(brain-v3-ui): Hotkey-Mapping als Docstring in _wire_hotkeys (Tier 3)"
```

---

## Task 8 — Brain-v2-Tab Refresh-Button (Tier 3)

**Files:**
- Modify: `ui/studio_brain/brain_v2_tab.py:24-25`
- Test: erweitere `test_brain_v3_phase5_widgets.py` (oder eigenes File falls die Phase-5-Datei v2-Material lieber meidet)

- [ ] **Step 8.1: Re-Read** (Datei oben in Verifizierung schon gelesen, Z.24 = `self._refresh_btn = QPushButton(...)`)

- [ ] **Step 8.2: Failing Test** (statisch, kein QApp-Boot nötig wenn Konstruktor-Smoke gemacht wird):

```python
def test_brain_v2_tab_refresh_button_has_tooltip(qt_app):
    """Tier-3: Refresh-Button im Brain-v2-Tab hat Tooltip."""
    from ui.studio_brain.brain_v2_tab import BrainV2Tab
    # session_factory=None -> refresh() faellt in den except-Pfad,
    # Widget-Konstruktion bleibt erfolgreich
    tab = BrainV2Tab(session_factory=None)
    assert tab._refresh_btn.toolTip()
    tab.deleteLater()
```

- [ ] **Step 8.3: Test FAILEN**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_brain_v2_tab_refresh_button_has_tooltip -v --tb=short
```
Expected: FAIL.

- [ ] **Step 8.4: Tooltip einfügen** (Z.24-25 erweitert)

```python
        self._refresh_btn = QPushButton("Refresh", self)
        self._refresh_btn.setToolTip(
            "Aktualisiert die Brain-v2-Statistiken (Entities, Facts, "
            "Decisions, Memories, Notes) aus der Brain-v2-DB. "
            "Auch der Ollama-Status wird neu gepingt."
        )
        self._refresh_btn.clicked.connect(self.refresh)
```

- [ ] **Step 8.5: Test PASSEN + Commit**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py::test_brain_v2_tab_refresh_button_has_tooltip -v --tb=short
git add ui/studio_brain/brain_v2_tab.py tests/test_services/test_brain_v3_phase5_widgets.py
git commit -m "feat(brain-v2-ui): tooltip fuer Refresh-Button (Tier 3 abgeschlossen)"
```

---

## Task 9 — Final-Lauf + Vault-Synthesis

- [ ] **Step 9.1: Voller Phase-5-Widget-Test-Lauf**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/test_brain_v3_phase5_widgets.py -v --tb=short
```
Expected: alle Tests gruen (7 Original + 8 neue Tooltip-Tests = 15 mindestens; Brain-v2-Tab-Test je nach Variante 1-2).

- [ ] **Step 9.2: Brain-V3-Subset-Regression**

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" -m pytest tests/test_services/ -k "brain_v3" --tb=short -q -m "not gui and not e2e and not slow"
```
Expected: bestehende 172 + neue Tooltip-Tests gruen.

- [ ] **Step 9.3: GUI-E2E manuell** (User-Verifikation)

App starten, Brain-V3-Stats-Panel öffnen, mit Maus über jeden Button hovern, prüfen dass Tooltips erscheinen und lesbar sind. Screenshot in `tests/qa_artifacts/tooltip_coverage_<datum>.png`.

```bash
"/c/Users/David Lochmann/Documents/PB_studio_Rebuild/PB_studio_Rebuild/.venv/Scripts/python.exe" start_pb_studio.py
```

- [ ] **Step 9.4: Vault-Synthesis-Doc**

Datei: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\2026-05-09-brain-ui-tooltip-coverage.md`

Inhalt:
- Was geändert (8 Tasks)
- Test-Ergebnisse (Pytest-Output)
- Coverage vorher/nachher (22.2% → 100%)
- Screenshot-Referenzen
- User-Verifikations-Status (PENDING bis David live geprueft hat)

- [ ] **Step 9.5: Repo-Synthesis spiegeln**

Datei: `docs/superpowers/synthesis/2026-05-09-brain-ui-tooltip-coverage.md` (Spiegelung des Vault-Docs).

```bash
git add docs/superpowers/synthesis/2026-05-09-brain-ui-tooltip-coverage.md
git commit -m "docs(brain-ui): synthesis Tooltip-Coverage 2026-05-09

- Tier 1-3 abgeschlossen, 27/27 Brain-UI-Widgets mit Tooltip
- 8 neue pytest-Tests
- Vault gespiegelt zu C:/Brain-Bug/projects/pb-studio/wiki/synthesis/"
```

- [ ] **Step 9.6: Status-Eintrag in 06_PHASES.md** (Phase-5-Sektion)

In `docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/06_PHASES.md` Phase 5 Sektion einen Sub-Punkt ergänzen:

```markdown
> **Tooltip-Coverage 2026-05-09 (autonomer Commander-Lauf):**
> Alle 27 interaktiven Brain-UI-Widgets (Feedback-Popup, Stats-Panel,
> Learning-Dialog, Brain-v2-Tab) mit Tooltips ausgestattet. 8 neue
> pytest-Tests in test_brain_v3_phase5_widgets.py. Coverage 22.2% -> 100%.
> Live-UI-Hover-Test: PENDING (User-Verifikation).
```

```bash
git add docs/superpowers/plans/2026-05-04-brain-v3-nvidia-plan/06_PHASES.md
git commit -m "docs(plan): tooltip-coverage-update in 06_PHASES.md Phase 5"
```

---

## Self-Review (vor Plan-Submit)

**1. Spec coverage:**
- Tier 1.1 Feedback-Buttons → Task 1 ✓
- Tier 1.2 Reset-Button → Task 2 ✓
- Tier 1.3 ProgressBar → Task 3 ✓
- Tier 2.1 ListWidget Doppelklick → Task 4 ✓
- Tier 2.2 Preview Play/Stop → Task 5 ✓
- Tier 2.3 Brain-v2-Tab → Task 6 ✓
- Tier 3.1 Hotkey-Docstring → Task 7 ✓
- Tier 3.2 Brain-v2-Refresh → Task 8 ✓

Alle 8 Tier-Punkte abgedeckt.

**2. Placeholder-Scan:** Keine `TBD` / `TODO` / `implement later` / `similar to Task N`. Jeder Step hat konkreten Code oder konkreten Befehl.

**3. Type-Konsistenz:**
- `FEEDBACK_TOOLTIPS` in Task 1 verwendet `dict[str, str]`, Keys = Rating-Strings aus `FEEDBACK_BUTTONS` Tuple-Index 0.
- Keine externe Symbole verwendet, die nicht in der echten Datei existieren (vorab per Read verifiziert).
- Test-Fixtures `qt_app` + `isolated_appdata` aus existierender Test-Datei wiederverwendet.

**4. Heikle Bereiche:**
- Task 6 (StudioBrainWindow) hat Fallback-Pfad falls Konstruktor in Tests crashed (Step 6.4b).
- Task 2 (Reset) Tooltip-Text ist mit QMessageBox-Text aus Z.181-185 abgestimmt (`axis_weights + pattern_correlations` + `Embedding-Cache bleibt`).
- Task 1 prüft per `grep` ob `FEEDBACK_BUTTONS` extern mutiert wird (Step 1.1) bevor die Konstante erweitert wird.

---

## Execution Handoff

**Plan complete and saved to** `docs/superpowers/plans/2026-05-09-brain-ui-tooltip-coverage.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Ich dispatche einen Subagent pro Task, Review zwischen Tasks, schnelle Iteration.

**2. Inline Execution** — Ich führe alle Tasks in dieser Session aus, Checkpoints für Review.

**Welche Variante?**
