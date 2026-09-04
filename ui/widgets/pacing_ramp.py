"""Schnittdichte als zwei Zahlen: Anfang und Ende.

Ersetzt das gezeichnete Kurvenfenster (``PacingCurveWidget``). Userauftrag vom
2026-09-04: *"mach die kurve weg und bau zwei zahlen anfang ende"*.

Die Messung davor (``test-report/loop7/kurven_messung.py``) hatte gezeigt, was
das Zeichenfenster wirklich leistete — und was nicht:

* Die Dichte ist der staerkste Regler im Pacing: Faktor 16 zwischen duenn
  (47 Cuts) und dicht (738 Cuts) auf demselben 337-Sekunden-Track.
* Ein Verlauf wird sauber umgesetzt: Rampe 0.0 -> 1.0 ergab ueber vier Viertel
  17 / 41 / 93 / 161 Cuts, die Gegenrampe spiegelbildlich 167 / 93 / 42 / 17.
* Feine Muster verpuffen: eine Welle mit vier Bergen ergab 85 / 85 / 86 / 82 —
  praktisch gleichmaessig. Bei 200 Stuetzstellen auf 337 s ist eine Stelle
  1.7 s breit, die Schnitte sitzen aber auf Beats im Abstand von ~0.46 s.

Der praktische Nutzen lag also vollstaendig im einfachen Verlauf von A nach B.
Genau den nehmen diese zwei Zahlen entgegen — ohne Zeichnen, ohne die Falle,
dass ein versehentlicher Strich die Schnittzahl verdoppelt (B-829).
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

# So viele Stuetzstellen hatte die gezeichnete Kurve. Die Zahl bleibt, damit
# alles dahinter unveraendert weiterlaeuft: calculate_cut_points rechnet den
# Beat-Zeitpunkt auf einen Index in dieser Liste um.
STUETZSTELLEN = 200

# Kein Verlauf gewaehlt -> die Grundeinstellung (Cut Rate) entscheidet allein.
NEUTRAL = 0.5


class PacingRampWidget(QWidget):
    """Zwei Zahlen statt einer gezeichneten Kurve.

    ``ramp_changed`` ersetzt das fruehere ``curve_changed`` und feuert unter
    denselben Bedingungen: sobald der Nutzer einen Wert aendert.
    """

    ramp_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._aktiv = False
        # Nur so hoch wie noetig. Das Kurven-Widget davor hatte
        # setMinimumHeight(280) und fuellte den Rest der Spalte; ohne diese
        # Vorgabe dehnte sich der Ersatz genauso und hinterliess denselben
        # Leerraum ueber den Zahlen (Userhinweis 2026-09-04).
        self.setSizePolicy(QSizePolicy.Policy.Preferred,
                           QSizePolicy.Policy.Maximum)
        self._build_ui()

    # ------------------------------------------------------------------
    # Aufbau
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(6)

        hinweis = QLabel(
            "Schnittdichte über den Track: 0.0 = sehr ruhig (16 Beats pro "
            "Schnitt), 1.0 = sehr dicht (jeder Beat). Dazwischen wird linear "
            "übergeblendet."
        )
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet("color:#9ca3af; font-size:11px;")
        v.addWidget(hinweis)

        zeile = QHBoxLayout()
        zeile.setSpacing(8)

        zeile.addWidget(self._beschriftung("Anfang"))
        self.spin_anfang = self._spinbox()
        # Der Tooltip-Audit prueft auch das interne Eingabefeld einer SpinBox,
        # deshalb wird es mitgesetzt (Regression aus Loop 8).
        self._mit_tooltip(
            self.spin_anfang,
            "Tempo am Anfang des Songs. 0.0 = ruhig, 1.0 = schnell, 0.5 = neutral.",
        )
        zeile.addWidget(self.spin_anfang)

        zeile.addSpacing(12)
        zeile.addWidget(self._beschriftung("Ende"))
        self.spin_ende = self._spinbox()
        self._mit_tooltip(
            self.spin_ende,
            "Tempo am Ende des Songs. Dazwischen wird linear ueberblendet.",
        )
        zeile.addWidget(self.spin_ende)

        zeile.addStretch(1)

        self.btn_zuruecksetzen = QPushButton("Zurücksetzen")
        self.btn_zuruecksetzen.setAccessibleName("Pacing-Verlauf zurücksetzen")
        self.btn_zuruecksetzen.setToolTip(
            "Verlauf abschalten — dann entscheidet allein die Cut Rate."
        )
        self.btn_zuruecksetzen.clicked.connect(self.reset_curve)
        zeile.addWidget(self.btn_zuruecksetzen)

        v.addLayout(zeile)

        self.lbl_wirkung = QLabel("")
        self.lbl_wirkung.setStyleSheet("color:#9ca3af; font-size:11px;")
        v.addWidget(self.lbl_wirkung)

        for spin in (self.spin_anfang, self.spin_ende):
            spin.valueChanged.connect(self._on_wert_geaendert)

        self._aktualisiere_wirkungstext()

    def _beschriftung(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet("color:#9ca3af; font-size:11px;")
        return lbl

    @staticmethod
    def _mit_tooltip(spin, text: str) -> None:
        """Setzt den Tooltip auf die SpinBox und ihr internes Eingabefeld."""
        spin.setToolTip(text)
        eingabe = spin.lineEdit()
        if eingabe is not None:
            eingabe.setToolTip(text)

    def _spinbox(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(0.0, 1.0)
        spin.setSingleStep(0.05)
        spin.setDecimals(2)
        spin.setValue(NEUTRAL)
        spin.setFixedWidth(80)
        return spin

    # ------------------------------------------------------------------
    # Zustand
    # ------------------------------------------------------------------
    def _on_wert_geaendert(self, _wert: float) -> None:
        # Erst eine echte Eingabe schaltet den Verlauf scharf. Solange beide
        # Werte auf NEUTRAL stehen und niemand sie angefasst hat, bleibt die
        # Cut Rate allein zustaendig — dieselbe Regel wie bei B-829.
        self._aktiv = True
        self._aktualisiere_wirkungstext()
        self.ramp_changed.emit()

    def _aktualisiere_wirkungstext(self) -> None:
        if not self._aktiv:
            self.lbl_wirkung.setText("Kein Verlauf aktiv — es gilt die Cut Rate.")
            return
        a, e = self.spin_anfang.value(), self.spin_ende.value()
        if abs(a - e) < 1e-9:
            self.lbl_wirkung.setText(
                f"Gleichmässig {a:.2f} über den ganzen Track."
            )
        else:
            richtung = "dichter" if e > a else "ruhiger"
            self.lbl_wirkung.setText(
                f"Von {a:.2f} auf {e:.2f} — wird zum Ende hin {richtung}."
            )

    # ------------------------------------------------------------------
    # Schnittstelle — namensgleich zum fruheren Kurven-Widget
    # ------------------------------------------------------------------
    def get_manual_override(self) -> list[float] | None:
        """Der Verlauf als Stuetzstellenliste, oder ``None``.

        ``None`` heisst: kein Verlauf gewaehlt, die Cut Rate entscheidet. Genau
        dieses Verhalten hatte das Kurven-Widget nach B-829, und der ganze
        Pfad dahinter verlaesst sich darauf.
        """
        if not self._aktiv:
            return None
        a, e = self.spin_anfang.value(), self.spin_ende.value()
        if STUETZSTELLEN == 1:
            return [a]
        schritt = (e - a) / (STUETZSTELLEN - 1)
        return [a + schritt * i for i in range(STUETZSTELLEN)]

    def get_all_densities(self) -> list[float]:
        """Die rohen Werte — immer, auch ohne aktiven Verlauf."""
        override = self.get_manual_override()
        if override is not None:
            return override
        return [NEUTRAL] * STUETZSTELLEN

    def reset_curve(self) -> None:
        """Verlauf abschalten und beide Zahlen auf neutral.

        Heisst weiterhin ``reset_curve``, weil der Projektwechsel genau diesen
        Namen ruft (B-837: die Kurve ueberlebte sonst den Projektwechsel).
        """
        for spin in (self.spin_anfang, self.spin_ende):
            spin.blockSignals(True)
            spin.setValue(NEUTRAL)
            spin.blockSignals(False)
        self._aktiv = False
        self._aktualisiere_wirkungstext()
        self.ramp_changed.emit()

    def set_duration(self, _dauer: float) -> None:
        """Der Verlauf ist relativ — die Trackdauer spielt keine Rolle mehr.

        Die Methode bleibt, weil zwei Aufrufer sie nutzen
        (``edit_workspace.py:179`` und ``:276``). Beim Kurven-Widget skalierte
        sie die Zeitachse der Zeichenflaeche.
        """
        return None

    def set_ramp(self, anfang: float, ende: float) -> None:
        """Verlauf setzen — für Tests und für ein späteres Laden aus dem Projekt."""
        for spin, wert in ((self.spin_anfang, anfang), (self.spin_ende, ende)):
            spin.blockSignals(True)
            spin.setValue(max(0.0, min(1.0, float(wert))))
            spin.blockSignals(False)
        self._aktiv = True
        self._aktualisiere_wirkungstext()
        self.ramp_changed.emit()
