"""Sub-Tab 'Pacing & Anker' im SCHNITT-Editor (Phase 06 / Task 6.1)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QSplitter,
    QComboBox, QSlider, QSpinBox, QLineEdit, QPushButton, QTreeWidget,
    QCheckBox,
)
from ui.widgets.pacing_ramp import PacingRampWidget


class SchnittTabPacingAnker(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 4)
        outer.setSpacing(4)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_pacing_column())
        splitter.addWidget(self._build_anker_column())
        splitter.setSizes([500, 500])
        outer.addWidget(splitter)

    def _build_pacing_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        v.addWidget(self._small_label("SCHNITTDICHTE"))
        # Userauftrag 2026-09-04: das gezeichnete Kurvenfenster ist ersetzt
        # durch zwei Zahlen. Die Messung davor zeigte, dass der praktische
        # Nutzen der Kurve vollstaendig im Verlauf von A nach B lag - feine
        # Muster mittelten sich weg (Welle mit vier Bergen: 85/85/86/82 Cuts).
        self.pacing_curve = PacingRampWidget()
        v.addWidget(self.pacing_curve)

        # Settings-Grid
        row1 = QHBoxLayout()
        row1.setSpacing(8)
        row1.addWidget(self._small_label("Cut Rate"))
        self.cut_rate_combo = QComboBox()
        self.cut_rate_combo.addItems(["1 Beat", "2 Beat", "4 Beat", "8 Beat", "16 Beat"])
        self.cut_rate_combo.setCurrentIndex(2)
        self.cut_rate_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # T4.5
        # B-840: Der Auto-Edit schneidet kein festes Raster mehr, sondern an
        # musikalischen Anlaessen (Section-Wechsel, Drops, Energiespruenge).
        # Diese Combo regelt seither die DICHTE dazwischen — der alte Text
        # "Grundraster" beschrieb ein Verhalten, das es nicht mehr gibt.
        self.cut_rate_combo.setToolTip(
            "Wirkung: Regelt die Schnittdichte. Geschnitten wird an "
            "musikalischen Stellen — Section-Wechsel und Drops sitzen immer, "
            "dieser Wert bestimmt, wie viel dazwischen liegt. "
            "Wann: Kleinere Werte fuer dichte, groessere fuer ruhige Schnitte. "
            "Ergebnis: bei 132 BPM etwa 300 Cuts (1 Beat) bis 38 Cuts (16 Beat) "
            "auf einen 5-Minuten-Track."
        )
        row1.addWidget(self.cut_rate_combo, stretch=1)
        row1.addWidget(self._small_label("Style"))
        self.style_combo = QComboBox()
        self.style_combo.addItems([
            "Standard", "Techno", "House", "Drum & Bass",
            "Hip-Hop", "Ambient", "Minimal", "Cinematic", "Festival",
        ])
        self.style_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # T4.5
        self.style_combo.setToolTip(
            "Wirkung: Waehlt ein Stilprofil fuer Clip-Auswahl und Energieverlauf. "
            "Wann: Nutze es passend zum Track-Genre oder zur Zielaesthetik. "
            "Ergebnis: Pacing-Gewichte werden fuer diesen Stil voreingestellt."
        )
        row1.addWidget(self.style_combo, stretch=1)
        row1.addWidget(self._small_label("Breakdown"))
        self.breakdown_combo = QComboBox()
        self.breakdown_combo.addItems(["halve", "force16", "none"])
        self.breakdown_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # T4.5
        self.breakdown_combo.setToolTip(
            "Wirkung: Steuert Schnitte in ruhigen Breakdown-Abschnitten. "
            "Wann: Nutze es, wenn Breakdowns weniger hektisch wirken sollen. "
            "Ergebnis: halve verdoppelt den Abstand im Breakdown, force16 "
            "vervierfacht ihn, none behandelt ihn wie jede andere Passage."
        )
        row1.addWidget(self.breakdown_combo, stretch=1)
        v.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        row2.addWidget(self._small_label("Reaktivität"))
        self.reactivity_slider = QSlider(Qt.Orientation.Horizontal)
        self.reactivity_slider.setRange(0, 100)
        self.reactivity_slider.setValue(50)
        self.reactivity_slider.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # T4.5
        self.reactivity_slider.setToolTip(
            "Wirkung: Bestimmt wie stark Audio-Energie die Schnittdichte bewegt. "
            "Wann: Niedrig fuer stabile Montage, hoch fuer energiegetriebene Drops. "
            "Ergebnis: 0 bleibt ruhig, 100 reagiert stark auf Energie."
        )
        row2.addWidget(self.reactivity_slider, stretch=1)
        self.reactivity_spin = QSpinBox()
        self.reactivity_spin.setRange(0, 100)
        self.reactivity_spin.setSuffix("%")
        self.reactivity_spin.setValue(50)
        self.reactivity_spin.setFocusPolicy(Qt.FocusPolicy.StrongFocus)  # T4.5
        self.reactivity_spin.setToolTip(
            "Wirkung: Setzt die Energie-Reaktivitaet exakt in Prozent. "
            "Wann: Nutze es fuer reproduzierbare Feineinstellung. "
            "Ergebnis: Gleicher Wert erzeugt denselben Reaktivitaetsgrad."
        )
        self.reactivity_spin.lineEdit().setToolTip(self.reactivity_spin.toolTip())
        row2.addWidget(self.reactivity_spin)
        v.addLayout(row2)

        row2b = QHBoxLayout()
        row2b.setSpacing(8)
        row2b.addWidget(self._small_label("Übergänge"))
        self.transition_combo = QComboBox()
        # Reihenfolge fix (0=Crossfade, 1=Cut) — Index-Mapping in
        # edit_workspace/workspace_setup haengt daran. Default = Harte Beat-Cuts
        # (B: crossfade-Export ist bei langen Timelines noch limitiert, B9).
        self.transition_combo.addItems([
            "Automatische Crossfades (experimentell)", "Harte Beat-Cuts",
        ])
        self.transition_combo.setCurrentIndex(1)
        self.transition_combo.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.transition_combo.setToolTip(
            "Wirkung: Bestimmt ob Schnitte weiche Überblendungen (Crossfades) "
            "erhalten oder harte Bildschnitte (Cuts) sind.\n"
            "Hinweis: Harte Beat-Cuts sind der stabile Standard. Automatische "
            "Crossfades sind experimentell und beim Export langer Timelines "
            "(viele Segmente) derzeit noch limitiert (Fix folgt mit B9)."
        )
        row2b.addWidget(self.transition_combo, stretch=1)
        v.addLayout(row2b)

        row3 = QHBoxLayout()
        row3.addWidget(self._small_label("Vibe"))
        self.vibe_input = QLineEdit()
        self.vibe_input.setPlaceholderText("z.B. 'dunkel, strobo, club'")
        self.vibe_input.setToolTip(
            "Wirkung: Gibt Auto-Edit eine textliche visuelle Richtung. "
            "Wann: Nutze es fuer Mood wie dunkel, strobo, club oder natur. "
            "Ergebnis: Die Richtung kann in Pacing-/Auswahlentscheidungen einfliessen."
        )
        row3.addWidget(self.vibe_input, stretch=1)
        v.addLayout(row3)

        # NEUBAU-VOLLINTEGRATION T2.1 (USE-007): LLM-Pacing per UI schaltbar.
        # Persistiert sofort im SettingsStore (Panel hat keinen OK-Button);
        # Controller liest die Werte beim Auto-Edit aus dem Store.
        row4 = QHBoxLayout()
        # NEUBAU-VOLLINTEGRATION T1.1 (USE-001): Studio-Brain-Pipeline als
        # persistentes Setting (vorher nur nackte Env-Var, die niemand
        # setzte). Env-Var PB_USE_STUDIO_BRAIN_PIPELINE bleibt Override.
        self.chk_studio_brain = QCheckBox("Studio-Brain")
        self.chk_studio_brain.setToolTip(
            "Wirkung: Das lernende Studio-Brain (PacingPipeline + "
            "DecisionRecorder) entscheidet den Schnitt mit und protokolliert "
            "jede Entscheidung. "
            "Wann: AN fuer lernenden Schnitt inkl. Decision-Explorer-Daten. "
            "Ergebnis: mem_pacing_run/mem_decision werden befuellt; "
            "Env-Var PB_USE_STUDIO_BRAIN_PIPELINE uebersteuert."
        )
        self.chk_llm_strategist = QCheckBox("LLM-Strategist")
        self.chk_llm_strategist.setToolTip(
            "Wirkung: Ein lokaler LLM (Ollama) erstellt vor dem Schnitt einen "
            "Pacing-Plan pro Song-Abschnitt. "
            "Wann: Fuer experimentell smartere Section-Strategien. "
            "Ergebnis: Cut-Dichte-Plan kommt vom LLM statt nur aus der Heuristik."
        )
        # B-952 (Userentscheidung 2026-08-31): musikgetriebener Schnitt war im
        # Code auf True voreingestellt und nirgends abschaltbar. Damit wurde der
        # LLM-Strategist bei JEDEM Lauf uebersprungen (seine Section-Map wird in
        # diesem Modus nicht gelesen, siehe pacing_service.py:857-866) — die
        # Checkbox daneben versprach also etwas, das nie eintrat (B-928).
        self.chk_musikgetrieben = QCheckBox("Musikgetriebener Schnitt")
        self.chk_musikgetrieben.setToolTip(
            "Wirkung: Geschnitten wird, wenn die Musik einen Grund liefert — "
            "Section-Wechsel, Drops, Energiespruenge — statt nach festem "
            "Beat-Raster. "
            "Wann: AN fuer lange, ruhige Einstellungen; AUS fuer gleichmaessige "
            "Raster-Schnitte. "
            "Ergebnis: AUS macht ausserdem den LLM-Strategist wirksam, der im "
            "musikgetriebenen Modus uebersprungen wird (kostet ~85 s pro Lauf)."
        )
        self.chk_llm_pacing = QCheckBox("LLM-EDL-Pacing")
        self.chk_llm_pacing.setToolTip(
            "Wirkung: Ollama schlaegt die Schnittliste (EDL) direkt vor. "
            "Wann: Experimentell; braucht laufendes Ollama. "
            "Ergebnis: Alternative Cut-Liste aus LLM-Reasoning."
        )
        try:
            from services.settings_store import (
                get_ollama_settings, get_settings_store,
            )
            _store = get_settings_store()
            # T1.1: Studio-Brain-Setting laden + sofort persistieren
            self.chk_studio_brain.setChecked(bool(_store.get_nested(
                "pacing", "use_studio_brain", default=False)))
            self.chk_studio_brain.toggled.connect(
                lambda on: get_settings_store().set_nested(
                    "pacing", "use_studio_brain", value=bool(on)))
            # Haken-2-Fix (User 2026-07-17): Checkbox standardmaessig AN,
            # konsistent mit dem Gate in edit_workspace.
            self.chk_llm_strategist.setChecked(bool(_store.get_nested(
                "pacing", "use_llm_strategist", default=True)))
            self.chk_llm_pacing.setChecked(bool(_store.get_nested(
                "pacing", "use_llm_pacing", default=False)))
            # B-952: Default True — das bisherige Verhalten bleibt, solange
            # niemand den Haken entfernt.
            self.chk_musikgetrieben.setChecked(bool(_store.get_nested(
                "pacing", "musikgetriebener_schnitt", default=True)))
            self.chk_musikgetrieben.toggled.connect(
                lambda on: get_settings_store().set_nested(
                    "pacing", "musikgetriebener_schnitt", value=bool(on)))
            self.chk_llm_strategist.toggled.connect(
                lambda on: get_settings_store().set_nested(
                    "pacing", "use_llm_strategist", value=bool(on)))
            self.chk_llm_pacing.toggled.connect(
                lambda on: get_settings_store().set_nested(
                    "pacing", "use_llm_pacing", value=bool(on)))
            # Voraussetzungs-Check ohne Netz-Call im UI-Thread: Ollama muss
            # in den Einstellungen aktiviert sein, sonst Checkboxen gesperrt.
            if not get_ollama_settings().get("enabled", False):
                for _chk in (self.chk_llm_strategist, self.chk_llm_pacing):
                    _chk.setEnabled(False)
                    _chk.setToolTip(
                        "Deaktiviert: Ollama ist in den Einstellungen "
                        "ausgeschaltet (Einstellungen > LLM Backend)."
                    )
        except Exception:  # Settings duerfen den Tab-Aufbau nie brechen
            pass
        row4.addWidget(self.chk_musikgetrieben)
        row4.addWidget(self.chk_studio_brain)
        row4.addWidget(self.chk_llm_strategist)
        row4.addWidget(self.chk_llm_pacing)
        # T2.5.6 (FR-S4-5): A/B-Gewichts-Vergleich (ab_runner) als UI
        self.btn_ab_compare = QPushButton("A/B-Gewichte testen")
        self.btn_ab_compare.setToolTip(
            "Wirkung: Vergleicht zwei Scorer-Gewichtsprofile auf dem "
            "Kandidatenpool (reine Analyse, kein Eingriff). "
            "Wann: Zum Austarieren von Energy-/Mood-/Stem-Gewichten. "
            "Ergebnis: Zeigt, welchen Clip jedes Profil waehlen wuerde."
        )
        self.btn_ab_compare.setAccessibleName("A/B-Gewichtsvergleich oeffnen")
        self.btn_ab_compare.clicked.connect(self._open_ab_compare)
        row4.addWidget(self.btn_ab_compare)
        row4.addStretch(1)
        v.addLayout(row4)

        action_row = QHBoxLayout()
        action_row.addStretch(1)
        self.btn_regenerate = QPushButton("Mit neuen Pacing-Einstellungen generieren")
        self.btn_regenerate.setObjectName("btn_accent")
        self.btn_regenerate.setFixedHeight(30)
        # B-833: Der Tooltip versprach neu berechnete Clips und die Beruecksichtigung
        # von Stil- und Ankerwerten. Tatsaechlich laeuft dieser Button in denselben
        # Codepfad wie "Timeline generieren" im Editor-Kopf: er zeichnet nur die
        # Cut-Linien neu, legt keine Clips an und liest weder Anker noch Style.
        self.btn_regenerate.setToolTip(
            "Wirkung: Zeichnet die Cut-Linien mit den aktuellen Pacing-Werten neu — "
            "eine Vorschau, identisch zu 'Timeline generieren' im Editor-Kopf. "
            "Wann: Nutze es nach Aenderung von Cut Rate, Breakdown oder Reaktivitaet, "
            "um die Schnittpunkte vorab zu sehen. "
            "Ergebnis: Nur Cut-Linien in der Timeline. Es werden KEINE Clips erzeugt, "
            "ersetzt oder verschoben und nichts gespeichert — zum tatsaechlichen "
            "Schneiden 'Auto-Edit' verwenden."
        )
        self.btn_regenerate.setAccessibleName("Timeline mit neuen Pacing-Einstellungen generieren")
        self.btn_regenerate.setStyleSheet(
            "QPushButton#btn_accent {"
            " background:#d4a44a; color:#0a0d12; font-weight:700;"
            " border:none; border-radius:4px; padding:0 14px;"
            "}"
            "QPushButton#btn_accent:hover { background:#f0c866; }"
        )
        action_row.addWidget(self.btn_regenerate)
        v.addLayout(action_row)

        # Der Platz, den frueher die 280 px hohe Zeichenflaeche einnahm, sammelt
        # sich jetzt unten statt zwischen den Bedienzeilen (Userhinweis
        # 2026-09-04: "den leerraum schliessen").
        v.addStretch(1)

        return col

    def _open_ab_compare(self) -> None:
        """T2.5.6: A/B-Vergleichs-Dialog oeffnen (lazy Import)."""
        try:
            from ui.dialogs.ab_compare_dialog import ABCompareDialog
            dlg = ABCompareDialog(self)
            dlg.exec()
        except Exception as exc:  # Dialog darf den Tab nie crashen
            import logging
            logging.getLogger(__name__).warning(
                "A/B-Dialog nicht startbar: %s", exc)

    def _build_anker_column(self) -> QWidget:
        col = QWidget()
        v = QVBoxLayout(col)
        v.setContentsMargins(8, 6, 8, 6)
        v.setSpacing(6)

        v.addWidget(self._small_label("ANKER (feste Audio-Video-Sync-Punkte)"))
        self.anchor_list = QTreeWidget()
        self.anchor_list.setHeaderLabels(["Zeit", "Video", "Label", "Gewicht"])
        self.anchor_list.setSortingEnabled(True)
        self.anchor_list.setToolTip(
            "Wirkung: Zeigt feste Audio-Video-Sync-Punkte. "
            "Wann: Nutze Anker fuer wichtige Drops, Vocals oder Bildtreffer. "
            "Ergebnis: Auto-Edit soll diese Punkte synchron halten."
        )
        self.anchor_list.setAccessibleName("Audio-Video-Ankerliste")
        v.addWidget(self.anchor_list, stretch=1)

        toolbar = QHBoxLayout()
        self.btn_add_anchor = QPushButton("+ Anker")
        self.btn_add_anchor.setToolTip(
            "Wirkung: Fuegt einen festen Sync-Punkt hinzu. "
            "Wann: Nutze es bei Drops, Vocals oder Bildmomenten, die exakt sitzen muessen. "
            "Ergebnis: Dieser Punkt kann beim Auto-Edit als harte Orientierung dienen."
        )
        self.btn_add_anchor.setAccessibleName("Sync-Anker hinzufuegen")
        self.btn_remove_anchor = QPushButton("− Anker")
        self.btn_remove_anchor.setToolTip(
            "Wirkung: Entfernt den ausgewaehlten Sync-Punkt. "
            "Wann: Nutze es bei falschen oder nicht mehr benoetigten Ankern. "
            "Ergebnis: Auto-Edit beruecksichtigt diesen Anker nicht mehr."
        )
        self.btn_remove_anchor.setAccessibleName("Sync-Anker entfernen")
        self.btn_sync_anchors = QPushButton("Sync")
        self.btn_sync_anchors.setToolTip(
            "Wirkung: Synchronisiert Anker mit Timeline und aktueller Medienauswahl. "
            "Wann: Nutze es nach manuellen Aenderungen an Clips oder Ankern. "
            "Ergebnis: Audio- und Video-Anker liegen wieder aufeinander."
        )
        self.btn_sync_anchors.setAccessibleName("Sync-Anker synchronisieren")
        for b in (self.btn_add_anchor, self.btn_remove_anchor, self.btn_sync_anchors):
            b.setFixedHeight(24)
            toolbar.addWidget(b)
        toolbar.addStretch(1)
        v.addLayout(toolbar)

        self.btn_learn_ai = QPushButton("Als KI-Lernregel speichern")
        self.btn_learn_ai.setToolTip(
            "Wirkung: Speichert den ausgewaehlten Anker als Lernsignal. "
            "Wann: Nutze es, wenn eine Sync-Entscheidung kuenftig bevorzugt werden soll. "
            "Ergebnis: Spaetere Auto-Edits koennen diese Wahl staerker beruecksichtigen."
        )
        self.btn_learn_ai.setAccessibleName("Anker als KI-Lernregel speichern")
        self.btn_learn_ai.setFixedHeight(24)
        v.addWidget(self.btn_learn_ai)

        return col

    @staticmethod
    def _small_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#98a2b1; font-size:9px; font-weight:700; letter-spacing:1px;")
        return lbl
