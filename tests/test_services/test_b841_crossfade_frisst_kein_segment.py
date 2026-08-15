"""B-841: Ein Crossfade durfte so lang werden wie das Segment selbst.

Der Clamp in `services/export_service.py` begrenzte den Overlap auf die VOLLE
Slotlaenge beider Nachbarn. Wird er so lang wie ein Segment, ist dessen
eigener Beitrag zum Bild null — das Segment verschwindet, das Video wird
kuerzer als das Audio.

Seit die Segmente durch den musikgetriebenen Schnitt kuerzer sind, ist das
kein Randfall mehr. `SECTION_CROSSFADE_MAP` vergibt fuer BUILDUP 1,0 s bei
einer Mindestdauer von 0,33 s, fuer COOLDOWN 4,0 s bei 2,62 s.
"""

from __future__ import annotations

import inspect

from services.pacing_beat_grid import SECTION_CROSSFADE_MAP, SECTION_MIN_DURATION


def _clamp_quelle() -> str:
    from services import export_service

    quelle = inspect.getsource(export_service)
    start = quelle.find("B-841")
    assert start > 0, "der B-841-Clamp fehlt"
    return quelle[start - 500:start + 900]


def test_clamp_nutzt_die_halbe_slotlaenge():
    text = _clamp_quelle()
    assert "_base / 2.0" in text, (
        "der Overlap wird nicht auf die halbe Slotlaenge des abgehenden "
        "Segments begrenzt"
    )
    assert "/ 2.0" in text.split("_slot(video_segments[_i + 1])")[1][:20], (
        "der Overlap wird nicht auf die halbe Slotlaenge des aufgehenden "
        "Segments begrenzt"
    )


def test_rechnung_haelt_bei_kurzen_segmenten():
    """Nachrechnen: ein 0,33-s-Segment darf hoechstens 0,165 s Overlap bekommen."""
    for slot in (0.33, 0.65, 1.31, 2.62, 3.18):
        for wunsch in SECTION_CROSSFADE_MAP.values():
            overlap = max(0.0, min(wunsch, 2.0, slot / 2.0, slot / 2.0))
            assert overlap <= slot / 2.0 + 1e-9
            assert slot - overlap >= slot / 2.0 - 1e-9, (
                f"von einem {slot}s-Segment bleiben nach {overlap}s Overlap "
                "weniger als die Haelfte uebrig"
            )


def test_die_kollision_ist_real():
    """Gegenprobe: es gibt Sections, deren Crossfade laenger ist als ihr Minimum."""
    kollisionen = {
        name: (SECTION_CROSSFADE_MAP[name], SECTION_MIN_DURATION[name])
        for name in SECTION_CROSSFADE_MAP
        if name in SECTION_MIN_DURATION
        and SECTION_CROSSFADE_MAP[name] > SECTION_MIN_DURATION[name]
    }
    assert kollisionen, (
        "keine Kollision mehr — dann kann dieser Test entfallen"
    )
    assert "BUILDUP" in kollisionen


def test_kein_segment_verschwindet_vollstaendig():
    """Der Kern: nach dem Overlap muss immer Bild uebrig bleiben."""
    for slot in (0.2, 0.33, 1.0, 5.0):
        overlap = max(0.0, min(4.0, 2.0, slot / 2.0, slot / 2.0))
        rest = slot - overlap
        assert rest > 0.0, f"{slot}s-Segment verschwindet vollstaendig"
