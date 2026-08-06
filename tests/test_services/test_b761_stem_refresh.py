"""B-761: StemPlayer-Konsolenspam und redundante Reloads waehrend Analyse.

Root Cause: Jeder Medien-Tabellen-Refresh (B-253-Bridge feuert pro
Analyse-Schritt) endet in `_update_stem_workspace`. Der druckt die
"[StemPlayer] Track #N geladen"-Zeile bei JEDEM Aufruf — obwohl der
Player identische Stem-Pfade gar nicht neu oeffnet — und wiederholt die
Beatgrid-Onset-BLOB-Query jedes Mal.

Vertraege:
1. Konsole meldet "geladen" nur bei tatsaechlich neuem Ladeziel.
2. Onset-Query/update_analysis wird nicht wiederholt, wenn dasselbe Ziel
   bereits mit vorhandenen Onsets geliefert wurde.
3. B-355-Schutz: Solange Onsets noch fehlen, wird weiter nachgefragt
   (spaet eintreffende Beat-Analyse erreicht den Onsets-Subtab).
4. Trackwechsel setzt alles zurueck.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session as DBSession

from database import engine, AudioTrack, Beatgrid
from database.models import Project
from ui.controllers.stems import StemsController


class _FakePlayer:
    """Nachbau des StemPlayer-Guard-Verhaltens: load_stems ist idempotent."""

    def __init__(self):
        self.duration = 5531.0
        self.load_calls = 0

    def load_stems(self, stem_paths):
        self.load_calls += 1
        return True

    def stop(self):
        pass


class _Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        def _rec(*a, **k):
            self.calls.append((name, a))
        return _rec


class _StemsWS:
    def __init__(self):
        self.analyses = []

    def update_analysis(self, snapshot):
        self.analyses.append(snapshot)


class _Console:
    def __init__(self):
        self.lines = []

    def append(self, text):
        self.lines.append(text)


def _make_window():
    return SimpleNamespace(
        stem_player=_FakePlayer(),
        stem_workspace=_Recorder(),
        _schnitt_audio_binder=_Recorder(),
        _stems_ws=_StemsWS(),
        console_text=_Console(),
    )


@pytest.fixture()
def two_tracks():
    """Zwei AudioTracks: #1 mit Onset-Daten, #2 ohne Beatgrid-Zeile."""
    with DBSession(engine) as s:
        project = Project(name="b761", path="C:/x/b761")
        s.add(project)
        s.flush()
        t1 = AudioTrack(
            project_id=project.id, file_path="C:/x/a.wav", title="a",
            duration=5531.0,
            stem_vocals_path="C:/x/a_vocals.wav",
            stem_drums_path="C:/x/a_drums.wav",
            stem_bass_path="C:/x/a_bass.wav",
            stem_other_path="C:/x/a_other.wav",
        )
        t2 = AudioTrack(
            project_id=project.id, file_path="C:/x/b.wav", title="b",
            duration=100.0,
            stem_vocals_path="C:/x/b_vocals.wav",
            stem_drums_path=None, stem_bass_path=None, stem_other_path=None,
        )
        s.add_all([t1, t2])
        s.flush()
        s.add(Beatgrid(
            audio_track_id=t1.id, bpm=128.0, offset=0.0,
            onset_kick_data=b"\x01", onset_snare_data=b"\x02",
            onset_hihat_data=b"\x03",
        ))
        s.commit()
        ids = (t1.id, t2.id)
    yield ids
    with DBSession(engine) as s:
        s.query(Beatgrid).delete()
        s.query(AudioTrack).delete()
        s.query(Project).filter(Project.name == "b761").delete()
        s.commit()


def test_repeated_sync_prints_console_only_once(two_tracks):
    """Kernvertrag: identisches Ziel -> genau eine 'geladen'-Meldung."""
    t1, _ = two_tracks
    win = _make_window()
    ctrl = StemsController(win)
    for _ in range(5):
        ctrl._update_stem_workspace(t1)
    loaded_lines = [x for x in win.console_text.lines if "geladen" in x]
    assert len(loaded_lines) == 1, (
        f"Konsole meldete {len(loaded_lines)}x 'geladen' fuer dasselbe "
        f"unveraenderte Ziel: {win.console_text.lines}"
    )


def test_repeated_sync_skips_onset_query_when_onsets_present(two_tracks):
    """Onsets vorhanden -> zweiter Sync wiederholt update_analysis nicht."""
    t1, _ = two_tracks
    win = _make_window()
    ctrl = StemsController(win)
    ctrl._update_stem_workspace(t1)
    ctrl._update_stem_workspace(t1)
    assert len(win._stems_ws.analyses) == 1, (
        "update_analysis (inkl. Beatgrid-BLOB-Query) lief mehrfach fuer "
        "unveraendertes Ziel mit bereits vorhandenen Onsets"
    )


def test_missing_onsets_keep_refreshing(two_tracks):
    """B-355-Schutz: ohne Onset-Daten wird weiter nachgefragt."""
    _, t2 = two_tracks
    win = _make_window()
    ctrl = StemsController(win)
    ctrl._update_stem_workspace(t2)
    ctrl._update_stem_workspace(t2)
    assert len(win._stems_ws.analyses) == 2, (
        "Spaet eintreffende Onset-Daten wuerden den Onsets-Subtab nie "
        "erreichen, wenn hier nicht erneut abgefragt wird"
    )


def test_track_switch_resets_console_and_analysis(two_tracks):
    """Trackwechsel ist ein neues Ziel: Meldung + Analyse laufen wieder."""
    t1, t2 = two_tracks
    win = _make_window()
    ctrl = StemsController(win)
    ctrl._update_stem_workspace(t1)
    ctrl._update_stem_workspace(t2)
    ctrl._update_stem_workspace(t1)
    loaded_lines = [x for x in win.console_text.lines if "geladen" in x]
    assert len(loaded_lines) == 3, (
        f"Trackwechsel muss neu melden; erhalten: {win.console_text.lines}"
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
