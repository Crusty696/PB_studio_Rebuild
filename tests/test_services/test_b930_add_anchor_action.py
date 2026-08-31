"""B-930: Die Chat-Aktion "add_anchor" muss einen Anker anlegen koennen.

Vorher baute sie ``ClipAnchor(anchor_time=…, scene_id=…)`` — beide Felder gibt
es im Modell nicht. Jeder Aufruf endete in einem TypeError, den der
except-Block in eine Fehlermeldung verwandelte; ``clip_anchors`` blieb im
echten Projekt dauerhaft bei 0 Zeilen.

Hier wird der Modellvertrag festgenagelt. Der Durchstich durch die ganze
Aktion haengt an ``get_active_project_id()``, das auf der globalen Engine
arbeitet — der wurde stattdessen live in der App verifiziert (siehe
Bug-Eintrag B-930).
"""
from __future__ import annotations

import pytest

from database import ClipAnchor


def test_alte_feldnamen_existieren_nicht():
    """Die Ursache: so wie frueher gebaut, ist der Anker nicht konstruierbar."""
    with pytest.raises(TypeError, match="anchor_time"):
        ClipAnchor(timeline_entry_id=1, anchor_time=1.0, scene_id="x")


def test_neue_feldnamen_sind_die_richtigen():
    """Der Fix: mit den echten Spalten laesst sich der Anker bauen."""
    anker = ClipAnchor(timeline_entry_id=1, time_offset=4.0, label="szene-7")
    assert anker.time_offset == pytest.approx(4.0)
    assert anker.label == "szene-7"


def test_modell_hat_genau_diese_spalten():
    """Absicherung gegen erneutes Auseinanderlaufen von Code und Schema."""
    spalten = {c.name for c in ClipAnchor.__table__.columns}
    assert spalten == {"id", "timeline_entry_id", "time_offset", "label", "color"}


@pytest.mark.parametrize("timeline_zeit,clip_start,erwartet", [
    (14.0, 10.0, 4.0),   # Anker mitten im Clip
    (10.0, 10.0, 0.0),   # exakt am Clip-Anfang
    (2.0, 10.0, 0.0),    # vor dem Clip -> nie negativ
])
def test_offset_rechnung(timeline_zeit: float, clip_start: float, erwartet: float):
    """``time_offset`` ist relativ zum Clip-Start (ui/timeline.py:1009).

    Dieselbe Rechnung wie in add_anchor; ein negativer Offset wuerde den
    Marker ausserhalb des Clips platzieren.
    """
    assert max(0.0, timeline_zeit - clip_start) == pytest.approx(erwartet)
