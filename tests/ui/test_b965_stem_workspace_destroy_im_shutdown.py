"""B-965 — ``StemWorkspace.destroy_workspace()`` hatte keinen Aufrufer.

Gefunden am 2026-09-02 mit ``tools/inventory_audit.py`` (Kategorie "Methoden
ohne Aufrufer"). Die Methode setzt ``_is_being_destroyed`` — das Flag schaltet
in ``StemWorkspace.closeEvent`` den einzigen Zweig frei, der

* die sechs Transport-/Mixer-Signale trennt und
* die laufenden ``PeakWorker``-QThreads per ``quit()``/``wait(1000)`` beendet.

Ohne Aufrufer lief dieser Zweig nie: beim App-Ende blieben die Peak-Threads
laufen und die Signale verbunden. Gleiches Muster wie B-837 (``reset_curve``)
und B-937 (``set_status``).

Der Fix haengt den Aufruf in ``PBWindow.closeEvent`` (main.py, Schritt 8b) ein,
zwischen EmbeddingScheduler-Stop und ``ModelManager.unload()``.

Live-Beleg (logs/pb_studio.log, PID 4824):
``2026-09-02 18:51:53 [INFO] __main__: closeEvent: StemWorkspace endgueltig geschlossen``
— eingebettet in die vollstaendige Cleanup-Kette, direkt vor
``closeEvent: ModelManager.unload() synchron abgeschlossen``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def main_quelle() -> str:
    return (REPO_ROOT / "main.py").read_text(encoding="utf-8", errors="replace")


def _close_event_block(quelle: str) -> str:
    """Der Rumpf von ``PBWindow.closeEvent``.

    Abgegrenzt am naechsten ``def`` auf gleicher Einrueckung, damit ein Aufruf
    in einer anderen Methode den Test nicht faelschlich gruen macht.
    """
    start = quelle.index("def closeEvent(")
    rest = quelle[start:]
    weiter = re.search(r"\n    def \w+\(", rest[10:])
    return rest[: weiter.start() + 10] if weiter else rest


def test_der_shutdown_ruft_destroy_workspace(main_quelle):
    """Der Kern des Befunds."""
    block = _close_event_block(main_quelle)

    assert "destroy_workspace()" in block, (
        "closeEvent ruft destroy_workspace nicht — Peak-Threads laufen weiter"
    )


def test_der_aufruf_nimmt_den_richtigen_zugriffspfad(main_quelle):
    """Das Widget haengt nicht am Fenster, sondern im Schnitt-Tab.

    ``workspace_setup.py:573`` setzt ``self._stems_ws`` auf den Container
    ``StemsWorkspace``; die einzige ``StemWorkspace``-Instanz ist dessen
    ``.stem_widget`` (``tab_audio.py:88/89``). Ein Zugriff direkt auf ein
    ``stem_workspace``-Attribut des Fensters waere ein anderes Objekt.
    """
    block = _close_event_block(main_quelle)

    assert '"_stems_ws"' in block
    assert '"stem_widget"' in block


def test_der_aufruf_steht_vor_dem_modelmanager_unload(main_quelle):
    """Reihenfolge: erst Threads beenden, dann VRAM freigeben.

    Umgekehrt koennte ein noch laufender PeakWorker nach dem
    ``empty_cache()`` erneut belegen.
    """
    block = _close_event_block(main_quelle)

    assert block.index("destroy_workspace()") < block.index("ModelManager().unload()")


def test_der_aufruf_faengt_fehler_ab(main_quelle):
    """Ein Fehler hier darf die restliche Cleanup-Kette nicht abreissen."""
    block = _close_event_block(main_quelle)
    ab = block.index("destroy_workspace()")
    umgebung = block[ab - 1200 : ab + 400]

    assert "try:" in umgebung
    assert "except" in umgebung


def test_destroy_workspace_setzt_das_flag(qapp):
    """Verhaltensbeleg statt Quellcode-Guard: das Flag schaltet um."""
    from ui.widgets.stem_workspace import StemWorkspace

    ws = StemWorkspace()
    try:
        assert ws._is_being_destroyed is False

        ws.destroy_workspace()

        assert ws._is_being_destroyed is True
    finally:
        ws.deleteLater()


def test_ohne_destroy_workspace_bleibt_der_aufraeum_zweig_zu(qapp):
    """Beleg fuer die Wirkung: ``close()`` allein raeumt nicht auf.

    Genau deshalb war der fehlende Aufrufer ein Defekt und keine Stilfrage.
    """
    from ui.widgets.stem_workspace import StemWorkspace

    ws = StemWorkspace()
    try:
        ws.close()

        assert ws._is_being_destroyed is False
    finally:
        ws.deleteLater()


def test_die_einzige_instanz_haengt_im_schnitt_tab():
    """Beleg, dass es genau einen Ort gibt, an dem aufgeraeumt werden muss."""
    quelle = (REPO_ROOT / "ui" / "workspaces" / "schnitt" / "tab_audio.py").read_text(
        encoding="utf-8", errors="replace")

    assert "self.stem_workspace = self._stems_ws.stem_widget" in quelle
