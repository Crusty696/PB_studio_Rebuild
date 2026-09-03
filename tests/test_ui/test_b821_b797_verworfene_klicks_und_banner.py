"""B-821 und B-797 — zwei Reparaturen, die die Mutationsprobe als ungedeckt fand.

Gemessen am 2026-09-03 mit `tools/mutationsprobe.py`. Neutralisiert man den Fix,
bleibt die Suite grün:

    B-821  ui/controllers/audio_analysis.py:362  45 passed, 9 skipped
    B-821  ui/controllers/audio_analysis.py:558  45 passed, 9 skipped
    B-821  ui/controllers/audio_analysis.py:685  45 passed, 9 skipped
    B-797  ui/controllers/media_table.py:305     31 passed

**B-821:** Ein verworfener Klick muss im Logfile stehen. Ohne den Eintrag ist
ein „toter Button" im Support nicht rekonstruierbar — die Konsolenmeldung im
Fenster sieht der Support nicht, das Logfile schon.

**B-797:** Der Nenner des Verwendungs-Banners („Timeline nutzt X von N Clips")
kommt aus dem asynchron befüllten Pool-Model. Der Aufrufer berechnete das
Banner synchron beim Projektwechsel, also *vor* dem Nachladen — N blieb auf dem
Stand des alten Projekts stehen. Live belegt am 2026-08-11: „354 von 2", über
90 Sekunden und einen Tab-Wechsel hinweg.

Die Tests binden die echten Methoden an ein schlankes Ersatzobjekt, damit
keine Qt-Fenster nötig sind.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# B-821 — verworfene Klicks im Logfile
# ---------------------------------------------------------------------------

class _Konsole:
    def __init__(self):
        self.zeilen: list[str] = []

    def append(self, text):
        self.zeilen.append(text)


class _Statusleiste:
    def __init__(self):
        self.meldungen: list[str] = []

    def showMessage(self, text, dauer=0):
        self.meldungen.append(text)


class _Fenster:
    def __init__(self):
        self.console_text = _Konsole()
        self.status_bar = _Statusleiste()


class _AudioController:
    """Nur `_analyze_selected_audio` mit dem echten Methodenrumpf."""

    def __init__(self, auswahl=None):
        from ui.controllers.audio_analysis import AudioAnalysisController

        self.window = _Fenster()
        self._auswahl = auswahl
        self._analyze_selected_audio = (
            AudioAnalysisController._analyze_selected_audio.__get__(self))

    def _get_selected_audio_track(self):
        return self._auswahl


def test_b821_ein_verworfener_klick_steht_im_logfile(caplog):
    """Der Kern des Befunds."""
    c = _AudioController(auswahl=None)

    with caplog.at_level(logging.WARNING, logger="ui.controllers.audio_analysis"):
        c._analyze_selected_audio()

    warnungen = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnungen, "kein WARNING im Logfile — der tote Button bleibt unsichtbar"
    assert "verworfen" in warnungen[0].getMessage().lower()


def test_b821_der_nutzer_sieht_zusaetzlich_konsole_und_statusleiste():
    """Das Logfile ersetzt die Rückmeldung im Fenster nicht, es ergänzt sie."""
    c = _AudioController(auswahl=None)

    c._analyze_selected_audio()

    assert c.window.console_text.zeilen, "keine Konsolenmeldung"
    assert c.window.status_bar.meldungen, "keine Statusleisten-Meldung"


def test_b821_bei_gueltiger_auswahl_wird_nicht_gewarnt(caplog):
    """Gegenprobe: der Guard darf nicht immer feuern.

    Der Aufruf läuft nach dem Guard in den echten Analysepfad und wirft dort;
    entscheidend ist allein, dass bis dahin keine Verwerfungs-Warnung fällt.
    """
    c = _AudioController(auswahl={"id": 1, "file_path": "/a/1.mp3"})

    with caplog.at_level(logging.WARNING, logger="ui.controllers.audio_analysis"):
        try:
            c._analyze_selected_audio()
        except Exception:
            pass

    verworfen = [r for r in caplog.records if "verworfen" in r.getMessage().lower()]
    assert not verworfen


@pytest.mark.parametrize("zeile,text", [
    (362, "Analyse-Klick verworfen"),
    (558, "Klick verworfen"),
    (685, "Klick verworfen"),
])
def test_b821_alle_drei_guards_loggen(zeile, text):
    """Quellcode-Guard für die beiden Stellen ohne Verhaltenstest.

    `_analyze_all_v2_batch` und `_analyze_all_sequential` brauchen eine echte
    DB-Session; hier zählt, dass die Warnung im jeweiligen Zweig steht.
    """
    quelle = (REPO_ROOT / "ui" / "controllers" / "audio_analysis.py").read_text(
        encoding="utf-8", errors="replace").splitlines()

    fenster = "\n".join(quelle[zeile - 4:zeile + 4])
    assert "logger.warning" in fenster, f"kein logger.warning um Zeile {zeile}"
    assert text in fenster


def test_b821_die_drei_stellen_behalten_ihren_marker():
    quelle = (REPO_ROOT / "ui" / "controllers" / "audio_analysis.py").read_text(
        encoding="utf-8", errors="replace")

    assert quelle.count("B-821") >= 3


# ---------------------------------------------------------------------------
# B-797 — Verwendungs-Banner nach dem Pool-Reload nachziehen
# ---------------------------------------------------------------------------

class _EditWorkspace:
    def __init__(self):
        self.nachgezogen = 0

    def _refresh_timeline_usage_marking(self):
        self.nachgezogen += 1


class _MediaFenster:
    def __init__(self):
        self.edit_workspace = _EditWorkspace()
        self._media_ws = None


class _MediaController:
    """Nur der B-797-Block, mit dem echten Rumpf von `_apply_refreshed_data`."""

    def __init__(self):
        self.window = _MediaFenster()

    def banner_nachziehen(self, videos):
        """Der Block aus `_apply_refreshed_data`, wortgleich nachgebaut.

        Ein direkter Aufruf der echten Methode zöge den gesamten Tabellen-Reload
        mit; der Quellcode-Guard unten hält dafür fest, dass der Block dort
        unverändert steht.
        """
        try:
            _video_total = len(videos)
            if _video_total != getattr(self, "_usage_banner_video_total", None):
                self._usage_banner_video_total = _video_total
                self.window.edit_workspace._refresh_timeline_usage_marking()
        except (AttributeError, RuntimeError):
            pass


def test_b797_das_banner_wird_nach_dem_reload_nachgezogen():
    c = _MediaController()

    c.banner_nachziehen(["a", "b", "c"])

    assert c.window.edit_workspace.nachgezogen == 1


def test_b797_bei_unveraenderter_poolgroesse_kein_zweiter_query():
    """Sonst liefe der synchrone Timeline-Query bei jedem Reload im GUI-Thread."""
    c = _MediaController()

    c.banner_nachziehen(["a", "b"])
    c.banner_nachziehen(["a", "b"])

    assert c.window.edit_workspace.nachgezogen == 1


def test_b797_eine_geaenderte_poolgroesse_zieht_erneut_nach():
    """Der Kern: „354 von 2" entstand, weil N vom alten Projekt stehenblieb."""
    c = _MediaController()

    c.banner_nachziehen(["a", "b"])
    c.banner_nachziehen(["a"])

    assert c.window.edit_workspace.nachgezogen == 2


def test_b797_der_block_steht_unveraendert_im_produktivcode():
    """Quellcode-Guard — der Verhaltenstest oben baut den Block nur nach."""
    quelle = (REPO_ROOT / "ui" / "controllers" / "media_table.py").read_text(
        encoding="utf-8", errors="replace")

    start = quelle.index("def _apply_refreshed_data")
    ende = quelle.find("\n    def ", start + 10)
    block = quelle[start:ende if ende != -1 else len(quelle)]

    assert "_usage_banner_video_total" in block

    # Der Aufruf MIT Empfaenger. Die blosse Zeichenkette
    # "_refresh_timeline_usage_marking()" steht zwei Zeilen darueber auch im
    # erklaerenden Kommentar - ein Guard darauf bleibt gruen, selbst wenn der
    # Aufruf entfernt wird. Genau das ist am 2026-09-03 passiert: die
    # Mutationsprobe meldete die Stelle weiterhin als UNGEDECKT, obwohl dieser
    # Test angeblich dafuer da war.
    assert "self.window.edit_workspace._refresh_timeline_usage_marking()" in block
    assert "B-797" in block
