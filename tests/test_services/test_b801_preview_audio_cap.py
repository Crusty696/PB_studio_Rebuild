"""B-801: die Quick-Preview darf nicht die komplette Audiodatei aufbereiten.

Live-Befund 2026-08-11: ``export_preview`` mit ``duration_limit=10.0`` brach
nach einem harten 300-s-ffmpeg-Timeout in der LUFS-Normalisierung ab. Ursache
war nicht die Normalisierung selbst, sondern ihr Input: das Audio wurde auf die
volle Dauer des Timeline-Eintrags geschnitten — bei einem DJ-Mix als einem
einzigen Eintrag 92 Minuten. Ein Zwei-Pass-``loudnorm`` darueber ist nicht in
300 s zu schaffen, und die Vorschau lieferte nie ein Ergebnis.

Getestet wird der Deckel in ``_prepare_audio_entry_for_timeline`` — auf der
Ebene der ffmpeg-Argumente, weil dort entschieden wird, wie viel Audio
tatsaechlich durch die Normalisierung laeuft. Kein echtes ffmpeg noetig.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services import export_service


class _Entry(SimpleNamespace):
    pass


@pytest.fixture()
def captured_ffmpeg(monkeypatch):
    """Faengt die ffmpeg-Argumente ab, statt wirklich zu encodieren."""
    calls: list[list[str]] = []

    def _fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return True

    monkeypatch.setattr(export_service, "_run_ffmpeg", _fake_run)
    return calls


def _duration_arg(cmd: list[str]) -> float:
    """Liest den Wert hinter ``-t`` aus der ffmpeg-Kommandozeile."""
    return float(cmd[cmd.index("-t") + 1])


def test_b801_preview_caps_audio_duration(captured_ffmpeg, tmp_path):
    """Der Deckel muss den langen Eintrag auf das Preview-Fenster kuerzen."""
    src = tmp_path / "mix.wav"
    src.write_bytes(b"RIFF")
    entry = _Entry(id=1, start_time=0.0, end_time=5520.0,
                   source_start=0.0, source_end=None)

    export_service._prepare_audio_entry_for_timeline(
        str(src), entry, 5520.0, [], max_duration=12.0,
    )

    assert captured_ffmpeg, "B-801: es wurde gar kein Zuschnitt ausgefuehrt."
    dur = _duration_arg(captured_ffmpeg[0])
    assert dur == pytest.approx(12.0), (
        f"B-801: Preview bereitet {dur:.1f}s Audio auf statt 12s — genau "
        "dieser Input liess die LUFS-Normalisierung in den 300s-Timeout laufen."
    )


def test_b801_full_export_stays_unbounded(captured_ffmpeg, tmp_path):
    """Ohne Deckel muss der echte Export weiter die volle Laenge nehmen.

    Der Fix darf ausschliesslich die Vorschau betreffen — beim finalen Export
    ist die Normalisierung ueber das ganze Material genau richtig.
    """
    src = tmp_path / "mix.wav"
    src.write_bytes(b"RIFF")
    # source_start 3.0 + volle Eintragsdauer muss in die Quelldatei passen,
    # sonst greift die Bereichspruefung in services/export/_common.py.
    entry = _Entry(id=1, start_time=0.0, end_time=5520.0,
                   source_start=3.0, source_end=None)

    export_service._prepare_audio_entry_for_timeline(
        str(src), entry, 5600.0, [],
    )

    assert captured_ffmpeg
    dur = _duration_arg(captured_ffmpeg[0])
    assert dur > 5000.0, (
        f"B-801-Regression: der volle Export kuerzt auf {dur:.1f}s — "
        "die Loudness-Messung waere dann nicht mehr materialgerecht."
    )


def test_b801_short_clip_is_not_touched_by_cap(captured_ffmpeg, tmp_path):
    """Ein Clip, der ohnehin kuerzer ist als der Deckel, bleibt unveraendert."""
    src = tmp_path / "short.wav"
    src.write_bytes(b"RIFF")
    entry = _Entry(id=1, start_time=0.0, end_time=4.0,
                   source_start=0.0, source_end=None)

    result = export_service._prepare_audio_entry_for_timeline(
        str(src), entry, 4.0, [], max_duration=12.0,
    )

    assert result == str(src), (
        "B-801: ein 4s-Clip wurde unnoetig durch ffmpeg geschickt, obwohl der "
        "12s-Deckel gar nicht greift."
    )
    assert not captured_ffmpeg
