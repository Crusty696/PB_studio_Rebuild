"""B-976 — zwei Zahlen statt gezeichneter Kurve.

Userauftrag vom 2026-09-04: *"mach die kurve weg und bau zwei zahlen anfang
ende"*. Davor ging eine Messung (`test-report/loop7/kurven_messung.py`), die
zeigte, was das Zeichenfenster leistete:

    ohne Kurve (Referenz)     185 Cuts   Viertel: [47, 46, 47, 45]
    dicht 1.0 ueberall        738 Cuts   Viertel: [186, 185, 186, 181]
    duenn 0.0 ueberall         47 Cuts   Viertel: [12, 12, 11, 12]
    Rampe 0.0 -> 1.0          312 Cuts   Viertel: [17, 41, 93, 161]
    Rampe 1.0 -> 0.0          319 Cuts   Viertel: [167, 93, 42, 17]
    Welle (4 Berge)           338 Cuts   Viertel: [85, 85, 86, 82]

Zwei Befunde daraus:

* Der Verlauf von A nach B kommt sauber an — die Rampen spiegeln sich.
* Feine Muster verpuffen. Die Welle mit vier Bergen ergab eine praktisch
  gleichmässige Verteilung. Bei 200 Stützstellen auf 337 s ist eine Stelle
  1.7 s breit, die Schnitte sitzen aber auf Beats im Abstand von ~0.46 s.

Der praktische Nutzen lag damit vollständig im einfachen Verlauf — genau den
nehmen die zwei Zahlen entgegen.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def widget(qapp):
    from ui.widgets.pacing_ramp import PacingRampWidget

    w = PacingRampWidget()
    try:
        yield w
    finally:
        w.deleteLater()


# ---------------------------------------------------------------------------
# Grundverhalten
# ---------------------------------------------------------------------------

def test_ohne_eingabe_gilt_die_cut_rate(widget):
    """Der Kern von B-829: kein Verlauf heisst `None`, nicht `[0.5]*200`.

    Ein flaches `[0.5]*200` verdoppelte die Schnittzahl (185 -> 369), obwohl
    der Nutzer nichts wollte.
    """
    assert widget.get_manual_override() is None


def test_eine_eingabe_schaltet_den_verlauf_scharf(widget):
    widget.set_ramp(0.2, 0.9)

    override = widget.get_manual_override()
    assert override is not None
    assert len(override) == 200


def test_der_verlauf_geht_linear_von_anfang_nach_ende(widget):
    widget.set_ramp(0.0, 1.0)
    werte = widget.get_manual_override()

    assert werte[0] == pytest.approx(0.0)
    assert werte[-1] == pytest.approx(1.0)
    assert werte[99] == pytest.approx(0.4975, abs=0.01)
    # streng monoton steigend
    assert all(b > a for a, b in zip(werte, werte[1:]))


def test_die_gegenrampe_faellt_streng_monoton(widget):
    widget.set_ramp(1.0, 0.0)
    werte = widget.get_manual_override()

    assert werte[0] == pytest.approx(1.0)
    assert werte[-1] == pytest.approx(0.0)
    assert all(b < a for a, b in zip(werte, werte[1:]))


def test_gleiche_werte_ergeben_eine_flache_dichte(widget):
    widget.set_ramp(0.8, 0.8)
    werte = widget.get_manual_override()

    assert all(w == pytest.approx(0.8) for w in werte)


def test_werte_werden_auf_null_bis_eins_begrenzt(widget):
    widget.set_ramp(-5.0, 99.0)

    assert widget.spin_anfang.value() == pytest.approx(0.0)
    assert widget.spin_ende.value() == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Schnittstelle zum bestehenden Pfad
# ---------------------------------------------------------------------------

def test_reset_curve_schaltet_den_verlauf_ab(widget):
    """Heisst weiter `reset_curve` — der Projektwechsel ruft diesen Namen.

    B-837: die Kurve überlebte sonst den Projektwechsel.
    """
    widget.set_ramp(0.1, 0.9)
    assert widget.get_manual_override() is not None

    widget.reset_curve()

    assert widget.get_manual_override() is None
    assert widget.spin_anfang.value() == pytest.approx(0.5)
    assert widget.spin_ende.value() == pytest.approx(0.5)


def test_der_projektwechsel_ruft_reset_curve():
    """Quellcode-Guard auf den Aufrufer."""
    quelle = (REPO_ROOT / "ui" / "controllers" / "project_management.py").read_text(
        encoding="utf-8", errors="replace")

    assert "pacing_curve.reset_curve()" in quelle


def test_get_all_densities_liefert_immer_werte(widget):
    """Der Zeichenpfad brauchte die rohen Werte auch ohne aktiven Verlauf."""
    ohne = widget.get_all_densities()
    assert len(ohne) == 200
    assert all(w == pytest.approx(0.5) for w in ohne)

    widget.set_ramp(0.0, 1.0)
    assert widget.get_all_densities()[-1] == pytest.approx(1.0)


def test_set_duration_bleibt_aufrufbar(widget):
    """Zwei Aufrufer nutzen sie (`edit_workspace.py:179` und `:276`)."""
    widget.set_duration(337.1)  # darf nicht werfen


def test_das_signal_feuert_bei_jeder_aenderung(widget):
    gefeuert = []
    widget.ramp_changed.connect(lambda: gefeuert.append(True))

    widget.set_ramp(0.3, 0.7)
    assert len(gefeuert) == 1

    widget.reset_curve()
    assert len(gefeuert) == 2


# ---------------------------------------------------------------------------
# Einbau
# ---------------------------------------------------------------------------

def test_der_pacing_tab_nutzt_die_rampe_nicht_mehr_die_kurve():
    quelle = (REPO_ROOT / "ui" / "workspaces" / "schnitt"
              / "tab_pacing_anker.py").read_text(encoding="utf-8", errors="replace")

    assert "PacingRampWidget()" in quelle
    assert "PacingCurveWidget()" not in quelle, "das Zeichenfenster steht noch im Tab"


def test_das_attribut_heisst_weiter_pacing_curve():
    """Sechs Stellen greifen darauf zu — der Name bleibt, das Widget wechselt."""
    quelle = (REPO_ROOT / "ui" / "workspaces" / "schnitt"
              / "tab_pacing_anker.py").read_text(encoding="utf-8", errors="replace")

    assert "self.pacing_curve = PacingRampWidget()" in quelle


def test_die_verdrahtung_kennt_das_neue_signal():
    quelle = (REPO_ROOT / "ui" / "controllers" / "workspace_setup.py").read_text(
        encoding="utf-8", errors="replace")

    assert '"ramp_changed"' in quelle
    assert "_generate_timeline" in quelle


def test_die_auswertung_holt_den_verlauf_unveraendert_ab():
    """`get_manual_override()` ist die Schnittstelle zum Pacing — sie bleibt."""
    quelle = (REPO_ROOT / "ui" / "controllers" / "edit_workspace.py").read_text(
        encoding="utf-8", errors="replace")

    assert "pacing_curve.get_manual_override()" in quelle


# ---------------------------------------------------------------------------
# Messbeleg: die Rampe erzeugt dieselbe Stützstellenliste wie zuvor
# ---------------------------------------------------------------------------

def test_die_rampe_entspricht_der_gemessenen_kurvenform(widget):
    """Gegenprobe zur Messung vom 2026-09-04.

    Dort wurde die Rampe als `[i / (N - 1) for i in range(N)]` erzeugt und
    ergab 312 Cuts mit der Verteilung [17, 41, 93, 161]. Das Widget muss
    genau diese Liste liefern, sonst misst die Messung etwas anderes als die
    App tut.
    """
    widget.set_ramp(0.0, 1.0)
    aus_widget = widget.get_manual_override()
    aus_messung = [i / 199 for i in range(200)]

    assert len(aus_widget) == len(aus_messung)
    assert all(a == pytest.approx(b) for a, b in zip(aus_widget, aus_messung))
