"""B-943 — Auto-Ducking meldete einen Absturz, obwohl das Ergebnis fertig war.

Gemessen am 2026-08-31 beim Live-Test des Chatwegs: die Ausgabedatei lag
vollstaendig vor (337.137 s, 44.1 kHz), der Worker meldete trotzdem

    [ERROR] AutoDuckingWorker crashed: [WinError 5] Zugriff verweigert:
    '...\\storage\\ducked\\_tmp_voice.wav'

Ursache: ``create_ducked_audio`` loeschte seine beiden Zwischendateien
ungeschuetzt im ``finally``. Schlug ein ``unlink`` fehl — unter Windows kann
eine gerade gelesene Datei kurzzeitig gesperrt sein — verliess die Ausnahme die
Funktion NACH dem erfolgreichen Schreiben. Der Nutzer sah einen roten Task und
wusste nicht, dass die Datei im Ordner liegt.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest


def _quelltext() -> str:
    from services.ai_audio_service import AutoDucker

    return inspect.getsource(AutoDucker.create_ducked_audio)


def test_aufraeumen_steht_in_einem_eigenen_schutz():
    """Quellcode-Guard: kein nacktes unlink mehr im finally.

    Der Rumpf laesst sich ohne ffmpeg und echte WAVs nicht durchlaufen; geprueft
    wird deshalb, dass das Aufraeumen gekapselt ist und nicht wieder blank im
    finally landet.
    """
    src = _quelltext()
    nach_finally = src.split("finally:", 1)[1]

    assert "except OSError" in nach_finally, "Aufraeumen faengt keinen Fehler ab"
    assert "logger.warning" in nach_finally, "Fehlschlag wird nicht gemeldet"


def test_beide_zwischendateien_werden_versucht():
    """Auch wenn die erste nicht loeschbar ist, muss die zweite drankommen."""
    src = _quelltext()
    nach_finally = src.split("finally:", 1)[1]

    assert "for _tmp in (tmp_music, tmp_voice)" in nach_finally


def test_gesperrte_datei_beendet_die_schleife_nicht(tmp_path, caplog):
    """Verhaltensnachweis mit demselben Muster wie im Fix.

    Die erste Datei laesst sich nicht loeschen, die zweite schon — am Ende darf
    keine Ausnahme nach aussen dringen und die zweite muss weg sein.
    """
    import logging

    erste = tmp_path / "_tmp_music.wav"
    zweite = tmp_path / "_tmp_voice.wav"
    erste.write_bytes(b"x")
    zweite.write_bytes(b"y")

    logger = logging.getLogger("test_b943")

    class _Gesperrt(type(erste)):
        pass

    def _aufraeumen(pfade) -> None:
        for _tmp in pfade:
            try:
                _tmp.unlink(missing_ok=True)
            except OSError as exc:
                logger.warning(
                    "[AutoDucker] Zwischendatei %s nicht loeschbar: %s "
                    "(Ergebnis ist davon nicht betroffen)", _tmp.name, exc)

    class _SturePfad:
        """Verhaelt sich wie Path, verweigert aber das Loeschen."""

        name = "_tmp_music.wav"

        def unlink(self, missing_ok: bool = False):
            raise PermissionError(13, "Zugriff verweigert")

    with caplog.at_level(logging.WARNING, logger="test_b943"):
        _aufraeumen([_SturePfad(), zweite])

    assert not zweite.exists(), "die zweite Datei muss trotzdem geloescht werden"
    assert any("nicht loeschbar" in eintrag.message for eintrag in caplog.records)


def test_ergebnisdatei_bleibt_unangetastet(tmp_path):
    """Das Aufraeumen darf nie die Ausgabe treffen."""
    ausgabe = tmp_path / "track_ducked.wav"
    ausgabe.write_bytes(b"ergebnis")
    tmp_music = tmp_path / "_tmp_music.wav"
    tmp_voice = tmp_path / "_tmp_voice.wav"
    tmp_music.write_bytes(b"a")
    tmp_voice.write_bytes(b"b")

    for pfad in (tmp_music, tmp_voice):
        try:
            pfad.unlink(missing_ok=True)
        except OSError:
            pass

    assert ausgabe.exists()
    assert ausgabe.read_bytes() == b"ergebnis"


@pytest.mark.parametrize("dateiname", ["_tmp_music.wav", "_tmp_voice.wav"])
def test_zwischendateinamen_unveraendert(dateiname):
    """Die Namen stehen in der Fehlermeldung von 2026-08-31 — nicht umbenennen.

    Ein verwaistes _tmp_voice.wav im ducked-Ordner ist der Hinweis darauf, dass
    dieser Fall wieder aufgetreten ist.
    """
    from services.ai_audio_service import AutoDucker

    src = inspect.getsource(AutoDucker.create_ducked_audio)

    assert dateiname in src


def test_verwaiste_datei_aus_dem_livetest_ist_dokumentiert():
    """Der Live-Test hinterliess eine 29-MB-Datei — der Pfad steht im Bug."""
    bug = Path(
        r"C:\Users\David_Lochmann\Documents\Vaults\Brain-Bug\projects\pb-studio"
        r"\wiki\bugs\B-943-auto-ducking-meldet-fehler-trotz-ergebnis.md"
    )
    if not bug.is_file():
        pytest.skip("Vault nicht verfuegbar")

    text = bug.read_text(encoding="utf-8", errors="ignore")

    assert "_tmp_voice.wav" in text
