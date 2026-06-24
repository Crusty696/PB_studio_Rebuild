"""B-569 — SCHNITT-Audio-Dropdown muss den A1-Lane-Track zeigen.

Originalbefund: Audio-ID (Zyce) lag in der A1-Lane (timeline_entries track="audio"),
das Dropdown zeigte aber einen anderen Track (ersten/analysierten). ``
_refresh_director_combos`` waehlte den Default unabhaengig vom A1-Inhalt.

Wiring-Guard im Stil von ``test_b321`` / ``test_b562``. Der behaviorale
Live-Beweis kommt aus dem pb-gui-tester (Zyce in A1 -> Dropdown == Zyce).
"""
from __future__ import annotations

import inspect


def test_refresh_director_combos_prefers_a1_audio_track() -> None:
    from ui.controllers.media_table import MediaTableController

    source = inspect.getsource(MediaTableController._refresh_director_combos)

    # Auswahl muss den tatsaechlichen A1-Audio-Entry beruecksichtigen.
    assert 'track="audio"' in source or "track='audio'" in source, (
        "B-569-Regression: _refresh_director_combos muss den A1-Audio-Entry "
        "(timeline_entries track=audio) fuer die Dropdown-Auswahl heranziehen."
    )
    assert "a1_audio_index" in source
    assert "findData" in source
