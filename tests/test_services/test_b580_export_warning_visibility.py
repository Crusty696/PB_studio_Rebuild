"""B-580: Materialverlust beim Export muss den User erreichen.

Live-Messung 2026-08-09: ein soft-geloeschter Clip, der in der Timeline
liegt, wurde uebersprungen — der Export meldete trotzdem Erfolg und
lieferte ein Video von 4.0 s statt 6.0 s. Der Verlust stand
ausschliesslich im Logfile; ``export_timeline()`` gibt nur den Pfad
zurueck, ``progress_cb`` bekam nichts.

Der Export bricht weiterhin bewusst NICHT ab (B-693 heilt die Luecke
in-memory statt einen Totalabbruch zu erzwingen). Neu ist allein die
Sichtbarkeit.

Vertraege:
1. ``warning_cb`` wird bei uebersprungenen Segmenten mit einer
   sprechenden Meldung gerufen (Anzahl + Konsequenz).
2. Wird eine Luecke geschlossen, kommt zusaetzlich der A/V-Versatz an.
3. Ohne ``warning_cb`` bleibt das Verhalten unveraendert (nur Log) —
   Bestands-Callsites duerfen nicht brechen.
4. Ein defekter ``warning_cb`` darf den Export NIE kippen.
5. Ohne uebersprungene Segmente gibt es keine Warnung (kein Fehlalarm).
"""
from __future__ import annotations

import logging

import pytest

from services.export_service import _emit_export_warning


def test_warning_reaches_callback():
    seen: list[str] = []
    _emit_export_warning(seen.append, "2 von 3 Video-Segmenten fehlen")
    assert seen == ["2 von 3 Video-Segmenten fehlen"]


def test_missing_callback_is_noop():
    # Vertrag 3: Bestands-Callsites ohne warning_cb bleiben unberuehrt.
    _emit_export_warning(None, "egal")  # darf nicht werfen


def test_broken_callback_never_kills_export(caplog):
    def boom(_msg):
        raise RuntimeError("UI ist weg")

    with caplog.at_level(logging.WARNING):
        _emit_export_warning(boom, "1 Segment fehlt")
    assert "Export-warning_cb fehlgeschlagen" in caplog.text


@pytest.mark.parametrize(
    "source_line",
    [
        # Vertrag 1: Skip-Zweig meldet Anzahl UND Konsequenz.
        "Video-Segmenten fehlen",
        # Vertrag 2: Gap-Zweig meldet den A/V-Versatz.
        "Timeline-Luecke von",
    ],
)
def test_both_warning_sites_wired(source_line):
    """Beide Fundstellen im Export rufen den Callback wirklich auf.

    Source-Inspection, weil ein voller Export-Lauf ffmpeg + echte
    Mediendateien braucht; der Live-Nachweis lief separat.
    """
    import inspect

    import services.export_service as es

    src = inspect.getsource(es.export_timeline)
    assert source_line in src
    # Die Meldung muss auch tatsaechlich emittiert werden, nicht nur
    # als Text herumliegen.
    assert src.count("_emit_export_warning(") >= 2


def test_export_timeline_accepts_warning_cb():
    import inspect

    from services.export_service import export_timeline

    params = inspect.signature(export_timeline).parameters
    assert "warning_cb" in params
    # Default None -> Bestandsaufrufe ohne das Kwarg bleiben gueltig.
    assert params["warning_cb"].default is None
