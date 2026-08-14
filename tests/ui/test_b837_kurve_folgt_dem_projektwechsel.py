"""B-837: Die gezeichnete Pacing-Kurve ueberlebte den Projektwechsel.

Befund aus der Gegenpruefung 2026-08-14. ``reset_curve()``
(``ui/widgets/pacing_curve.py:39``) hatte im gesamten Produktivcode **keinen
Aufrufer** — ein grep ueber ``ui/`` und ``services/`` fand nur die Definition.
``_on_project_changed`` (``ui/controllers/project_management.py``) fasst die
Kurve nicht an, und das Widget wird einmalig in
``ui/workspaces/schnitt/tab_pacing_anker.py:34`` gebaut.

Folge: wer in Projekt A eine Kurve zeichnet und dann Projekt B oeffnet, hat
dort weiterhin die Kurve aus A. Da eine gezeichnete Kurve seit B-829 Vorrang
vor der Cut-Rate-Wahl hat (``get_manual_override``), bestimmt sie im neuen
Projekt den Schnitt — ohne dass ein Bezug dazu bestuende.

Kein Regress aus B-829: vorher wirkte die Kurve sogar ungezeichnet, also immer.
Der Fehler ist aelter und wurde durch den Fix nur sichtbar.

Nicht behoben und hier bewusst nicht getestet: eine gezeichnete Kurve wird
nirgends gespeichert. ``PacingProfile.manual_density_curve``
(``services/pacing_profile.py:42``) existiert als Feld, aber kein Codepfad
schreibt es in die Datenbank oder liest es zurueck. "Beim Projektwechsel laden"
setzt eine Persistenz voraus, die es nicht gibt.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")


@pytest.fixture
def kurve(qtbot):
    from ui.widgets.pacing_curve import PacingCurveWidget

    widget = PacingCurveWidget()
    qtbot.addWidget(widget)
    return widget


def _als_gezeichnet_markieren(widget) -> None:
    """Den Zustand herstellen, den ein echter Mausstrich hinterlaesst."""
    widget._density = [0.9] * widget._num_samples
    widget._user_edited = True


class TestZuruecksetzen:
    def test_reset_entfernt_die_nutzervorgabe(self, kurve):
        _als_gezeichnet_markieren(kurve)
        assert kurve.get_manual_override() is not None

        kurve.reset_curve()

        assert kurve.get_manual_override() is None, (
            "B-837: nach dem Zuruecksetzen darf keine Nutzervorgabe mehr "
            "gemeldet werden, sonst bleibt die Cut-Rate ueberstimmt."
        )

    def test_reset_stellt_den_ruhezustand_her(self, kurve):
        _als_gezeichnet_markieren(kurve)
        kurve.reset_curve()
        assert kurve.get_all_densities() == [0.5] * kurve._num_samples


class TestProjektwechsel:
    def test_projektwechsel_ruft_reset_curve(self):
        """Der eigentliche Defekt: die Kurve haengt an keinem Lebenszyklus.

        Geprueft wird der Quelltext von ``_on_project_changed``, weil ein
        echter Projektwechsel Datenbank, Timeline und Dashboard mitzieht.
        """
        import ast
        import inspect

        from ui.controllers import project_management

        quelle = inspect.getsource(project_management.ProjectManagementController._on_project_changed)
        baum = ast.parse(quelle.strip())

        aufrufe = {
            knoten.func.attr
            for knoten in ast.walk(baum)
            if isinstance(knoten, ast.Call) and isinstance(knoten.func, ast.Attribute)
        }
        assert "reset_curve" in aufrufe, (
            "B-837: _on_project_changed setzt die Pacing-Kurve nicht zurueck — "
            "eine im alten Projekt gezeichnete Kurve wirkt im neuen weiter."
        )

    def test_reset_ist_gegen_fehlendes_widget_abgesichert(self):
        """Der Aufruf darf den Projektwechsel nie scheitern lassen.

        Die Kurve gehoert dem Schnitt-Workspace; ist der noch nicht gebaut,
        fehlt das Attribut. Ein Absturz an dieser Stelle wuerde den gesamten
        Projektwechsel abbrechen.
        """
        import inspect

        from ui.controllers import project_management

        quelle = inspect.getsource(project_management.ProjectManagementController._on_project_changed)
        abschnitt = quelle[quelle.find("reset_curve") - 600:quelle.find("reset_curve") + 200]
        assert "try:" in abschnitt or "getattr" in abschnitt or "hasattr" in abschnitt, (
            "B-837: der reset_curve-Aufruf ist nicht abgesichert."
        )
