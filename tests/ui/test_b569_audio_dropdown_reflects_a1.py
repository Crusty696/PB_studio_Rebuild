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

    # B-577: Die A1-Lookup-Logik wurde in den gemeinsamen Helper
    # ``_a1_audio_combo_index`` extrahiert (von sync- UND async-Pfad genutzt).
    # _refresh_director_combos muss diesen Helper fuer die Auswahl heranziehen.
    combos_source = inspect.getsource(
        MediaTableController._refresh_director_combos
    )
    helper_source = inspect.getsource(
        MediaTableController._a1_audio_combo_index
    )

    # Auswahl muss den tatsaechlichen A1-Audio-Entry beruecksichtigen.
    assert 'track="audio"' in helper_source or "track='audio'" in helper_source, (
        "B-569-Regression: _a1_audio_combo_index muss den A1-Audio-Entry "
        "(timeline_entries track=audio) fuer die Dropdown-Auswahl heranziehen."
    )
    assert "a1_audio_index" in combos_source
    assert "_a1_audio_combo_index" in combos_source
    assert "findData" in helper_source
