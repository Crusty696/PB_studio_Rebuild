# Phase 5 Blueprint — PySide6-UI (4-Klick-Popup, Stats-Panel, Lern-Session)

> **🔴 STATUS 2026-05-05: TODO — BUILD-FROM-SCRATCH-MODE**
>
> Vor Beginn prüfen:
> 1. `ui/brain_v3/` sollte **NICHT existieren** (sonst → Verify-Mode statt Build).
> 2. Phase 4 muss DONE sein — diese Phase konsumiert die 5 in-process
>    Methoden des `BrainV3Service` aus `services/brain_v3/brain_v3_service.py`.
> 3. V1/V2-UI (`ui/studio_brain_window.py`, `ui/studio_brain/brain_v2_tab.py`)
>    darf umgebaut werden (User-Direktive 2026-05-05, F2 — Plan-Doc 02 #24
>    aktualisiert), aber **pro Refactor Live-Verifikation der V1/V2-UI-
>    Funktion** erforderlich. Standard-Vorgehen: Brain V3 bekommt einen
>    NEUEN Tab `ui/brain_v3/` parallel zu V1/V2 — V1/V2 bleibt als
>    Default unangetastet, ausser ein Refactor wird explizit verlangt.
> 4. Hotkeys 1–4: vor Implementation prüfen ob diese Keys schon belegt sind
>    (z.B. für Playhead-Navigation in MainWindow).
>
> **Architektur-Direktive (User 2026-05-05, F1):** PB Studio Rebuild ist
> reine PySide6-Desktop-App. Phase 5 baut **keinen** HTTP-Client, ruft
> **kein** REST-Endpoint, kennt **kein** `localhost:8765`. Stattdessen
> wird der `BrainV3Service`-Wrapper (Phase 4) direkt aus PySide6-Slots
> in-process aufgerufen — mit `QThread` / `QtConcurrent.run` fuer alles,
> was nicht UI-Thread-tauglich ist.

## 1. Ziel + Erfolgsdefinition

**Ziel:** User kann auf Cuts klicken (4-Klick-Popup mit Hotkeys 1–4),
sieht Brain-V3-Lerneffekt im Stats-Panel, kann Lern-Session-Dialog mit
15 unsichersten Cuts durchklicken, kann Brain V3 zurücksetzen.

**Erfolg = wahr wenn:** Realer Mix + 500 Clips importiert, User klickt
50+, Stats-Panel zeigt Lerneffekt nachweisbar (Top-5-Buckets gefüllt),
erneuter Pacing-Run unterscheidet sich vom ersten Run, Reset stellt
Cold-Start wieder her.

**Aufwand-Schätzung:** 3–5 Tage.

---

## 2. Voraussetzungen

| Voraussetzung | Status erwartet |
|---|---|
| Phase 4 (Pacing-Integration + in-process BrainV3Service) DONE | ✓ Vorbedingung |
| `cut.metadata.brain_v3_scores` ist im Cut-Output enthalten | aus Phase 4 |
| `services/brain_v3/brain_v3_service.py` mit `BrainV3Service`-Klasse importierbar | aus Phase 4 |
| PySide6 6.11 installiert (Workspace-Bestand) | ✓ |
| Hauptfenster + Tab-System existiert | im Workspace prüfen |

---

## 3. Architektur

```text
ui/brain_v3/                            ←── NEUER Subfolder, V3-isoliert
├── __init__.py
├── brain_v3_tab.py                     ←── Hauptcontainer (QTabWidget-Tab)
├── stats_panel.py                      ←── Top-Buckets + Cold-Start-Status
├── learning_session_dialog.py          ←── 15-Cut-Dialog mit Audio/Video-Preview
├── reset_dialog.py                     ←── Two-Step-Confirmation
├── cut_feedback_popup.py               ←── 4-Klick-Popup für Timeline-Cuts
└── confidence_overlay.py               ←── Dünner Balken über jedem Cut
                                              (rot=unsicher, grün=sicher)

ui/main_window.py                       ←── EINE Zeile: addTab(BrainV3Tab(...), "Brain V3")
ui/timeline/cut_item.py (oder Äquivalent) ←── EINE Modifikation:
                                              Right-Click + Hotkeys 1-4 → CutFeedbackPopup
```

**Daten-Fluss (in-process, kein HTTP):**

```text
TimelineCutItem  ──Right-Click──→ CutFeedbackPopup
                                       │
                                       ▼ Klick auf "Passt perfekt"
                                  brain_v3_service.feedback(
                                      BrainV3FeedbackRequest(...)
                                  )   ← Python-Methoden-Aufruf,
                                       direkt aus PySide6-Slot
                                       │
                                       ▼ FeedbackResponse
                                  Update ConfidenceOverlay
                                  (Farb-Übergang rot→grün)

BrainV3Tab.refresh()            ──→ brain_v3_service.stats()
                                       │
                                       ▼ BrainV3StatsResponse
                                  StatsPanel zeigt:
                                  - Total Klicks
                                  - Cold-Start: X/17 Achsen
                                  - Top-5 positive Buckets
                                  - Top-5 negative Buckets

BrainV3Tab.start_learning_session() ──→ brain_v3_service.learning_session()
                                       │
                                       ▼ BrainV3LearningSessionResponse
                                       (cuts: [15])
                                  LearningSessionDialog zeigt
                                  Cut 1/15 mit Audio+Video-Preview
                                  → User klickt 1-4 → service.feedback(...)
                                  → Cut 2/15 ...

BrainV3Tab.reset()              ──→ brain_v3_service.reset()  (ohne Token)
                                  Token erhalten
                                  ResetDialog (2-Step-Confirm)
                                  brain_v3_service.reset(
                                      BrainV3ResetConfirmRequest(token)
                                  )
```

**Threading-Hinweis:** lange laufende Methoden (`suggest`, gegebenenfalls
`learning_session`) werden in einem `QThread`-Worker ausgefuehrt, damit
der UI-Thread nicht blockiert. Schnelle Reads (`stats`, `feedback`)
duerfen synchron im Slot bleiben, sind aber wenn `>50 ms` ebenfalls
threaded — siehe AGENTS.md GUI-Freezing-Prevention.

---

## 4. Datei-für-Datei-Spezifikation

### 4.1 `ui/brain_v3/__init__.py`

```python
"""Brain V3 PySide6-UI — V3-isoliert, NICHT V1/V2-UI umbauen."""
```

### 4.2 `ui/brain_v3/cut_feedback_popup.py`

```python
from PySide6 import QtCore, QtGui, QtWidgets
from typing import Callable

from services.brain_v3.brain_v3_service import BrainV3Service
from services.brain_v3 import schemas as brain_schemas

RATING_LABELS = {
    "perfect":   "Passt perfekt (1)",
    "fits":      "Passt (2)",
    "not_quite": "Passt nicht ganz (3)",
    "no_match":  "Passt gar nicht (4)",
}

class CutFeedbackPopup(QtWidgets.QDialog):
    """4-Klick-Popup mit Hotkeys 1-4 für einen Timeline-Cut.

    Args:
        cut_id: int — wird in BrainV3FeedbackRequest verpackt
        on_rating_submitted: Callable[[str], None] — Callback (rating-string)
        service: BrainV3Service — in-process Fassade aus services/brain_v3
    """
    def __init__(self, cut_id: int, on_rating_submitted: Callable,
                 service: BrainV3Service, parent=None):
        super().__init__(parent)
        self.cut_id = cut_id
        self.on_rating = on_rating_submitted
        self.service = service
        self._build_ui()
        self._setup_hotkeys()

    def _build_ui(self):
        # 4 große QPushButtons untereinander mit RATING_LABELS
        # Esc-Hotkey schließt Popup
        ...

    def _setup_hotkeys(self):
        # Key_1, Key_2, Key_3, Key_4 → click corresponding button
        ...

    def _submit(self, rating: str):
        try:
            response = self.service.feedback(brain_schemas.BrainV3FeedbackRequest(
                cut_id=self.cut_id, rating=rating,
            ))
            self.on_rating(rating)
            self.accept()
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Brain V3", f"Feedback failed: {e}")
```

### 4.3 `ui/brain_v3/stats_panel.py`

```python
class StatsPanel(QtWidgets.QWidget):
    """Zeigt:
    - Total Klicks
    - Cold-Start-Status (X/17 Achsen aus Cold-Start)
    - Top-5 positive Buckets (axis, context_key, α, β)
    - Top-5 negative Buckets
    - Refresh-Button
    """
    def __init__(self, service: BrainV3Service, parent=None): ...
    def refresh(self) -> None:
        """Ruft service.stats() (in-process) und aktualisiert UI.
        Bei Latenz >50 ms via QThread, sonst synchron im UI-Thread."""
```

### 4.4 `ui/brain_v3/learning_session_dialog.py`

```python
class LearningSessionDialog(QtWidgets.QDialog):
    """Modaler Dialog mit 15 Cuts nacheinander.
    Pro Cut:
    - Audio-Snippet abspielen (von cut.start_time bis cut.end_time)
    - Video-Snippet preview
    - 4-Klick-Buttons + Hotkeys 1-4
    - Progress-Bar (1/15, 2/15, ...)
    """
    def __init__(self, service: BrainV3Service, parent=None):
        super().__init__(parent)
        self.service = service
        # learning_session() laeuft im QThread, weil Smart-Sampler-
        # Lookup ueber alle Cuts gehen kann
        self.cuts = self.service.learning_session().cuts  # 15 Cuts
        self.current_idx = 0
        self._build_ui()

    def _show_current_cut(self):
        # Lädt audio + video für self.cuts[self.current_idx]
        # Spielt mit QMediaPlayer ab
        ...

    def _on_rating(self, rating: str):
        # service.feedback(BrainV3FeedbackRequest(cut_id, rating))
        # current_idx += 1
        # Wenn current_idx == 15: schließen
```

### 4.5 `ui/brain_v3/reset_dialog.py`

```python
class ResetDialog(QtWidgets.QDialog):
    """Two-Step:
    1. Warning: "Brain V3 wird zurückgesetzt. Alle gelernten Gewichte gehen verloren."
       Buttons: "Abbrechen", "Weiter"
    2. Token wird empfangen via service.reset()  (ohne Token-Argument)
    3. Confirmation: "Wirklich zurücksetzen?"
       Buttons: "Abbrechen", "Ja, jetzt zurücksetzen"
    4. service.reset(BrainV3ResetConfirmRequest(token)) → status=reset_complete
    5. Success-Message
    """
    def __init__(self, service: BrainV3Service, parent=None): ...
```

### 4.6 `ui/brain_v3/confidence_overlay.py`

```python
class ConfidenceOverlay(QtWidgets.QWidget):
    """Dünner farbiger Balken über jedem Timeline-Cut.

    Farb-Mapping:
      confidence < 0.33  → rot   (unsicher / hohe Varianz)
      0.33 ≤ c < 0.66    → gelb
      c ≥ 0.66            → grün  (gelernt sicher)

    Wird gezeichnet via paintEvent() OBER den Timeline-Cuts.
    Höhe: 4 px. Position: oberhalb des Cut-Items.
    """
    def __init__(self, parent=None): ...

    def set_cut_confidences(self, cuts: list[dict]):
        """cuts hat brain_v3_scores_json + start_time + end_time"""
```

### 4.7 `ui/brain_v3/brain_v3_tab.py`

```python
from services.brain_v3.brain_v3_service import BrainV3Service

class BrainV3Tab(QtWidgets.QWidget):
    """Haupt-Tab im Hauptfenster (NEUER Tab, NICHT studio_brain_window umbauen).

    Layout:
        ┌──────────────────────────────────────┐
        │  StatsPanel                          │
        │  (Total Klicks, Cold-Start, Top-5)   │
        ├──────────────────────────────────────┤
        │  Buttons:                            │
        │  [ Lern-Session starten ]            │
        │  [ Brain V3 zurücksetzen ]           │
        └──────────────────────────────────────┘

    Architektur-Direktive (User 2026-05-05, F1): KEIN HTTP-Client,
    KEIN api_base_url, KEIN localhost:8765. Direkter Aufruf der
    in-process BrainV3Service-Instanz.
    """
    def __init__(self, service: BrainV3Service | None = None, parent=None):
        super().__init__(parent)
        # Optional Dependency-Injection; sonst wird Singleton aus
        # services/brain_v3 geholt
        self.service = service or _get_default_brain_v3_service()
        self.stats_panel = StatsPanel(self.service, self)
        self._build_ui()

    def open_learning_session(self):
        dialog = LearningSessionDialog(self.service, self)
        dialog.exec()
        self.stats_panel.refresh()

    def open_reset_dialog(self):
        dialog = ResetDialog(self.service, self)
        if dialog.exec() == QtWidgets.QDialog.Accepted:
            self.stats_panel.refresh()


def _get_default_brain_v3_service() -> BrainV3Service:
    """Singleton-Helper. Konstruktion mit echten Stores aus
    services/brain_v3.paths-Pfaden."""
    ...
```

### 4.8 App-Eingriffspunkte (V1/V2-naher Code, freigegeben)

#### Hauptfenster-Datei (Pfad vor Edit per Grep verifizieren — `ui/timeline.py` / `ui/workspaces/edit_workspace.py` o. ae.)

```python
# Im Hauptfenster-Init NACH studio_brain_window-Initialisierung:
from ui.brain_v3.brain_v3_tab import BrainV3Tab, _get_default_brain_v3_service
self._brain_v3_service = _get_default_brain_v3_service()
self.brain_v3_tab = BrainV3Tab(service=self._brain_v3_service, parent=self)
self.tab_widget.addTab(self.brain_v3_tab, "Brain V3")
```

#### Timeline-Cut-Item (Pfad per Grep verifizieren — z. B. `ui/timeline.py` `class TimelineCutItem`)

Hook in CutItem (QGraphicsItem oder QWidget):
```python
def mousePressEvent(self, event):
    if event.button() == QtCore.Qt.RightButton:
        from ui.brain_v3.cut_feedback_popup import CutFeedbackPopup
        popup = CutFeedbackPopup(
            cut_id=self.cut_id,
            on_rating_submitted=self._on_brain_v3_rating,
            service=self._brain_v3_service,  # injected, in-process
            parent=self.scene().views()[0] if self.scene() else None,
        )
        popup.exec()
        return
    super().mousePressEvent(event)

def _on_brain_v3_rating(self, rating: str):
    # Confidence-Overlay aktualisieren
    if self._confidence_overlay:
        self._confidence_overlay.refresh_for_cut(self.cut_id)
```

**Hotkeys 1-4 während Playback:** in MainWindow oder TimelineView:
```python
from services.brain_v3 import schemas as brain_schemas

def keyPressEvent(self, event):
    if event.key() in (QtCore.Qt.Key_1, QtCore.Qt.Key_2,
                       QtCore.Qt.Key_3, QtCore.Qt.Key_4):
        if self._currently_active_cut_id is not None:
            rating_map = {QtCore.Qt.Key_1: "perfect",
                          QtCore.Qt.Key_2: "fits",
                          QtCore.Qt.Key_3: "not_quite",
                          QtCore.Qt.Key_4: "no_match"}
            rating = rating_map[event.key()]
            self._brain_v3_service.feedback(brain_schemas.BrainV3FeedbackRequest(
                cut_id=self._currently_active_cut_id, rating=rating,
            ))
        return
    super().keyPressEvent(event)
```

---

## 5. SQL-Migrations

**Keine.** Phase 5 ist UI-only.

---

## 6. App-Eingriffspunkte — Audit-Trail

| Datei | Was geändert | Risk |
|---|---|---|
| `ui/main_window.py` | +1 Tab via addTab() | niedrig (additiv) |
| `ui/timeline/cut_item.py` | mousePressEvent + _on_brain_v3_rating | mittel (Right-Click-Pfad) |
| MainWindow.keyPressEvent | Hotkeys 1-4 für aktiven Cut | niedrig |

**Default: KEINE Änderungen** an `ui/studio_brain_window.py` (V1) oder
`ui/studio_brain/brain_v2_tab.py` (V2). Ausnahme nur bei explizit
verlangtem Refactor mit pro-Refactor Live-Verifikation der V1/V2-UI-
Funktion (User-Direktive 2026-05-05, F2).

---

## 7. Test-Spezifikation

PySide6-UI ist schwer pytest-bar (braucht Display oder offscreen-Mode).

### Smoke-Tests `tests/test_ui/test_brain_v3_ui.py` (mit `QT_QPA_PLATFORM=offscreen`)

- `test_cut_feedback_popup_constructs` — kein Crash bei __init__
- `test_cut_feedback_popup_hotkeys` — Key_1 emit→ on_rating("perfect") aufgerufen
- `test_stats_panel_renders_cold_start_state`
- `test_stats_panel_handles_service_exception_gracefully` — Mock-Service raises
- `test_brain_v3_tab_constructs`
- `test_reset_dialog_two_step_flow`
- `test_learning_session_dialog_n_15_cuts`
- `test_confidence_overlay_paints_correct_color` — confidence=0.2 → rot

### Manueller End-to-End-Test (kein Automatisierter)

```text
☐ App starten (start_pb_studio.bat)
☐ Realen Mix + 500 Clips importieren
☐ Pacing-Run mit "use_brain_v3" Checkbox aktiviert
☐ Cut rechts-klicken → Popup zeigt 4 Buttons + Hotkey-Hints
☐ Hotkey 1 ("Passt perfekt") → Popup schließt, Confidence-Overlay
   wird grüner für diesen Cut
☐ 50+ Klicks abgeben (gemischt)
☐ Brain V3 Tab öffnen → Stats-Panel zeigt:
   - Total Klicks > 0
   - Cold-Start-Status: x/17 Achsen aus Cold-Start raus
   - Top-5 positive + Top-5 negative Buckets gefüllt
☐ "Lern-Session starten" Button → Dialog zeigt 15 Cuts mit Audio+Video-Preview
☐ Alle 15 durchklicken → Dialog schließt, Stats refresht
☐ "Brain V3 zurücksetzen" → Two-Step-Confirmation
☐ Reset-Bestätigung → Stats sind wieder auf 0
☐ V1 (services/brain_service.py-Audit-View) ist UNVERÄNDERT funktional
☐ V2 (ui/studio_brain/brain_v2_tab.py) ist UNVERÄNDERT funktional
```

---

## 8. Definition of Done

```text
☐ Realer Mix + 500 Clips, 50+ Klicks abgegeben
☐ Stats-Panel zeigt Lerneffekt nachweisbar
☐ Lern-Session-Dialog spielt Audio+Video-Preview
☐ Reset funktioniert, danach wieder Cold-Start
☐ Hotkeys 1-4 funktionieren während Playback
☐ Confidence-Overlay färbt sich nach Klicks
☐ V1/V2-UI unverändert lauffähig (Regression-Smoke)
☐ ~10 Smoke-Tests grün (offscreen-Mode)
☐ Synthesis-Doc unter docs/superpowers/synthesis/
```

---

## 9. Risiken + Mitigationen

| Risiko | Mitigation |
|---|---|
| PySide6-Tests brauchen Display | `QT_QPA_PLATFORM=offscreen` setzen, MainWindow nur konstruieren+show, kein Echt-Render |
| 4-Klick-Popup blockiert UI während Playback | QDialog non-modal, Hotkeys funktionieren auch ohne Popup |
| BrainV3Service-Aufruf blockiert UI bei langsamer Methode | QtCore.QThread oder QtConcurrent.run fuer Service-Aufrufe (>50 ms) |
| Audio/Video-Preview im Lern-Session-Dialog ist komplex (Codecs) | QMediaPlayer mit nativem Backend; Fallback: Click → Browser-Open |
| Hotkeys 1-4 kollidieren mit App-Bestehenden-Shortcuts | vor Implementation in MainWindow.keyPressEvent prüfen welche Keys belegt sind |
| User klickt auf alten studio_brain_window-Tab → V1 wird gestartet | UNTOUCHED — alter Tab funktioniert weiterhin, neuer Tab "Brain V3" daneben |

---

## 10. Verifikations-Strategie

- **Smoke-Tests:** ~10 in `tests/test_ui/test_brain_v3_ui.py` (offscreen-Mode)
- **Manueller E2E:** Realer Mix + 500 Clips + 50 Klicks (siehe Sektion 7)
- **Regression:** Alter studio_brain_window Tab + brain_v2_tab müssen unverändert funktionieren
- **Service-Smoke:** alle UI→BrainV3Service-Aufrufe geben Pydantic-Responses ohne Exception zurueck (im Pytest mit Mock-`BrainV3Service`)

---

## 11. Reihenfolge der Implementation

```text
1. ui/brain_v3/__init__.py + Pfad-Setup (5 Min)
2. _get_default_brain_v3_service() Helper (in brain_v3_tab.py) (15 Min)
3. CutFeedbackPopup + Hotkey-Test (1 h) — direkter Service-Aufruf
4. StatsPanel + Test (1 h)
5. ResetDialog + Test (45 Min)
6. LearningSessionDialog + Audio/Video-Player (2 h)
7. ConfidenceOverlay (Custom-Paint) + Test (1 h)
8. BrainV3Tab (Haupt-Container) + Test (45 Min)
9. Hauptfenster-Datei: addTab + Hotkeys 1-4 (30 Min) — Pfad per Grep
10. Timeline-Cut-Item Right-Click-Hook (30 Min) — Pfad per Grep
11. Manueller E2E-Test mit echtem Mix (1-2 h)
12. Synthesis-Doc

Total: ~8-10 Stunden + Verifikation.
```

---

## Hinweis für Claude Code

**KRITISCH:** PySide6-Code. Vor jedem Edit:
1. `ui/`-Struktur im Workspace verstehen (gibt es schon ein Tab-System?
   QMainWindow oder QWidget-basiert? QTabWidget oder Custom?)
2. `studio_brain_window.py` und `brain_v2_tab.py` per Default UNTOUCHED
   lassen — Refactor nur bei explizitem User-Auftrag mit Live-Verifikation
3. Hotkeys 1-4: vor Implementation prüfen ob diese Keys schon belegt sind
   (z.B. für Playhead-Navigation)
4. QMediaPlayer für Audio/Video-Preview kann auf Windows codec-spezifische
   Probleme haben — teste mit echten Mix-Files vor Stable-Release

**Kein HTTP, kein REST-Client.** Phase 5 nutzt **ausschliesslich**
in-process Aufrufe an `BrainV3Service` (Phase 4). Wenn ein Code-
Vorschlag `requests.`, `httpx.`, `urllib.`, `BrainV3ApiClient`,
`http://` oder `localhost:8765` enthaelt, ist das Plan-Verstoss —
sofort stoppen, korrigieren.

**Service-Aufrufe** sollten async/threaded sein, nicht UI-blockierend
(QThreadPool oder QtConcurrent.run).
