"""B-620: Status-Inferenz darf keine JSON-Blob-Spalten mehr laden.

Live-Beleg 2026-07-13 (logs/freeze_stacks.log, E-Live-GUI-Test): waehrend
``infer_many_from_db`` lief, steckte der DB-Worker sekundenlang in
``json.loads`` von joined-/selectin-geladenen Relationship-Blobs
(``session.get(AudioTrack)`` zieht via ``lazy='joined'`` WaveformData
``band_low/mid/high`` und Beatgrid ``onset_*``/``energy_per_beat`` mit,
``session.get(VideoClip)`` via ``lazy='selectin'`` volle Scene-Rows inkl.
``keyframe_paths``/``embedding_indices``). Die C-JSON-Decodes hielten den
GIL -> Qt-Main-Thread fror 2-14s ein (E1/E3/E4/E9-Freezes, B-620).

Pins:
(a) Query-Shape: Kein von der Inferenz ausgeloestes SELECT laedt die
    grossen Blob-Spalten (siehe ``_AUDIO_BLOB_COLUMNS`` /
    ``_VIDEO_BLOB_COLUMNS``).
(b) Paritaet: Die geschriebenen AnalysisStatus-Rows (status,
    error_message, value_summary) sind identisch zum Verhalten vor dem
    Umbau — Fixture deckt volle Datenlage, leere Datenlage, Reconcile
    (error->done) und No-Touch (done bleibt done) ab.
"""

from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import event, select
from sqlalchemy.orm import Session

from database import (
    AnalysisStatus,
    AudioTrack,
    Beatgrid,
    Project,
    Scene,
    StructureSegment,
    VideoClip,
    WaveformData,
)

# Spalten, deren json.loads-Decode den GIL-Freeze verursachte (B-620).
# Sie duerfen von der Status-Inferenz nicht mehr selektiert werden.
_AUDIO_BLOB_COLUMNS = [
    "band_low",
    "band_mid",
    "band_high",
    "onset_kick_data",
    "onset_snare_data",
    "onset_hihat_data",
    "energy_per_beat",
    "stem_weighted_energy",
    "downbeat_positions",
    "energy_curve",
    "harmonic_tension_curve",
    "key_modulation_data",
    "transcription",
]

_VIDEO_BLOB_COLUMNS = [
    "keyframe_paths",
    "embedding_indices",
    "ai_tags",
]


@contextmanager
def _capture_selects(test_engine):
    statements: list[str] = []

    def _before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lower())

    event.listen(test_engine, "before_cursor_execute", _before)
    try:
        yield statements
    finally:
        event.remove(test_engine, "before_cursor_execute", _before)


def _patch_nullpool_session(test_engine, monkeypatch):
    from services import analysis_status_service as svc

    @contextmanager
    def _session():
        with Session(test_engine) as session:
            yield session

    monkeypatch.setattr(svc, "nullpool_session", _session)
    return svc


def _seed_full_audio(test_engine):
    """Audio-Track mit ALLEN Analyse-Artefakten inkl. grosser Blobs."""
    with Session(test_engine) as session:
        session.add(Project(id=1, name="P", path="."))
        session.add(AudioTrack(
            id=1,
            project_id=1,
            file_path="/a/1.mp3",
            duration=60.0,
            key="8A",
            key_confidence=0.9,
            lufs=-14.0,
            mood="dark",
            genre="psy",
            spectral_bands=[0.1, 0.2],
            energy_curve=[0.5] * 5000,
            harmonic_tension_curve=[0.1] * 5000,
            stem_vocals_path="vocals.wav",
            stem_drums_path="drums.wav",
        ))
        session.add(Beatgrid(
            audio_track_id=1,
            bpm=120.0,
            offset=0.0,
            beat_positions=[0.0, 0.5, 1.0],
            downbeat_positions=[0.0] * 1000,
            energy_per_beat=[0.5] * 5000,
            stem_weighted_energy=[0.5] * 5000,
            onset_kick_data=[[0.0, 1.0]] * 5000,
            onset_snare_data=[[0.0, 1.0]] * 5000,
            onset_hihat_data=[[0.0, 1.0]] * 5000,
        ))
        session.add(WaveformData(
            audio_track_id=1,
            num_samples=100,
            duration=60.0,
            band_low=[0.1] * 10000,
            band_mid=[0.2] * 10000,
            band_high=[0.3] * 10000,
        ))
        session.add(StructureSegment(
            audio_track_id=1,
            start_time=0.0,
            end_time=10.0,
            label="DROP",
            energy=0.8,
        ))
        # Audio 2: leere Datenlage (keine Artefakte, keine Analyse-Werte)
        session.add(AudioTrack(id=2, project_id=1, file_path="/a/2.mp3"))
        # Reconcile-Fall: error -> done
        session.add(AnalysisStatus(
            media_type="audio",
            media_id=1,
            step_key="lufs_analysis",
            status="error",
            error_message="boom",
        ))
        # No-Touch-Fall: done bleibt done, value_summary bleibt erhalten
        session.add(AnalysisStatus(
            media_type="audio",
            media_id=1,
            step_key="key_detection",
            status="done",
            value_summary={"key": "OLD", "confidence": 0.1},
        ))
        session.commit()


def _seed_videos(test_engine):
    with Session(test_engine) as session:
        session.add(Project(id=1, name="P", path="."))
        session.add(VideoClip(
            id=1,
            project_id=1,
            file_path="/v/1.mp4",
            duration=30.0,
            width=1920,
            height=1080,
            fps=30.0,
            codec="h264",
        ))
        session.add(Scene(
            video_clip_id=1,
            start_time=0.0,
            end_time=5.0,
            ai_caption={"description": "x"},
            keyframe_paths=["kf/0.jpg"] * 100,
            embedding_indices=list(range(100)),
            ai_tags=["tag"] * 100,
        ))
        session.add(Scene(
            video_clip_id=1,
            start_time=5.0,
            end_time=9.0,
            ai_caption=None,
        ))
        # Video 2: unvollstaendige Metadaten (duration fehlt), keine Scenes
        session.add(VideoClip(
            id=2,
            project_id=1,
            file_path="/v/2.mp4",
            width=1280,
            height=720,
            fps=25.0,
        ))
        session.commit()


def _status_rows(test_engine, media_type: str) -> dict:
    with Session(test_engine) as session:
        rows = session.execute(
            select(AnalysisStatus).where(AnalysisStatus.media_type == media_type)
        ).scalars().all()
        return {
            (row.media_id, row.step_key): (
                row.status,
                row.error_message,
                row.value_summary,
            )
            for row in rows
        }


# ---------------------------------------------------------------------------
# (a) Query-Shape: keine Blob-Spalten im Inferenz-Pfad
# ---------------------------------------------------------------------------

def test_b620_infer_many_audio_selects_no_blob_columns(test_engine, monkeypatch):
    svc = _patch_nullpool_session(test_engine, monkeypatch)
    _seed_full_audio(test_engine)

    with _capture_selects(test_engine) as statements:
        svc.infer_many_from_db("audio", [1, 2])

    selects = [s for s in statements if s.lstrip().startswith("select")]
    assert selects, "Inferenz muss ueberhaupt SELECTs feuern"
    for column in _AUDIO_BLOB_COLUMNS:
        offenders = [s for s in selects if column in s]
        assert not offenders, (
            f"B-620: Status-Inferenz laedt weiterhin Blob-Spalte '{column}' — "
            f"json.loads dieser Blobs hielt den GIL und fror den Qt-Main-Thread "
            f"ein. Offending SELECT:\n{offenders[0]}"
        )


def test_b620_infer_many_video_selects_no_blob_columns(test_engine, monkeypatch):
    svc = _patch_nullpool_session(test_engine, monkeypatch)
    _seed_videos(test_engine)

    with _capture_selects(test_engine) as statements:
        svc.infer_many_from_db("video", [1, 2])

    selects = [s for s in statements if s.lstrip().startswith("select")]
    assert selects, "Inferenz muss ueberhaupt SELECTs feuern"
    for column in _VIDEO_BLOB_COLUMNS:
        offenders = [s for s in selects if column in s]
        assert not offenders, (
            f"B-620: Status-Inferenz laedt weiterhin Scene-Blob-Spalte "
            f"'{column}'. Offending SELECT:\n{offenders[0]}"
        )


def test_b620_infer_single_audio_selects_no_blob_columns(test_engine, monkeypatch):
    """Auch der Einzel-Pfad infer_from_db (StatusPanel-Worker) bleibt blob-frei."""
    svc = _patch_nullpool_session(test_engine, monkeypatch)
    _seed_full_audio(test_engine)

    with _capture_selects(test_engine) as statements:
        svc.infer_from_db("audio", 1)

    selects = [s for s in statements if s.lstrip().startswith("select")]
    for column in _AUDIO_BLOB_COLUMNS:
        offenders = [s for s in selects if column in s]
        assert not offenders, (
            f"B-620: infer_from_db laedt weiterhin Blob-Spalte '{column}'. "
            f"Offending SELECT:\n{offenders[0]}"
        )


# ---------------------------------------------------------------------------
# (b) Paritaet: identische Status-Rows wie vor dem Umbau
# ---------------------------------------------------------------------------

def test_b620_audio_status_parity(test_engine, monkeypatch):
    """Erwartung = exaktes Verhalten der Vor-B-620-Implementierung.

    (Vor dem Umbau gegen den alten Code verifiziert — gleiche Fixture,
    gleiche Rows.)
    """
    svc = _patch_nullpool_session(test_engine, monkeypatch)
    _seed_full_audio(test_engine)

    svc.infer_many_from_db("audio", [1, 2])

    actual = _status_rows(test_engine, "audio")
    assert actual == {
        (1, "bpm_detection"): ("done", None, {"bpm": 120.0, "beats": 3}),
        (1, "waveform_analysis"): ("done", None, {"num_samples": 100}),
        # Vorbestehendes done bleibt unangetastet (inkl. altem value_summary)
        (1, "key_detection"): ("done", None, {"key": "OLD", "confidence": 0.1}),
        # error wird aus DB-Evidenz zu done reconciled, error_message geloescht
        (1, "lufs_analysis"): ("done", None, {"lufs": -14.0}),
        (1, "mood_genre_classify"): ("done", None, {"mood": "dark", "genre": "psy"}),
        (1, "spectral_analysis"): ("done", None, {"bands": 2}),
        (1, "structure_detection"): ("done", None, {"segments": 1}),
        (1, "stem_separation"): ("done", None, {"stems": 2}),
        # Audio 2 (leer): keine einzige Row
    }


def test_b620_video_status_parity(test_engine, monkeypatch):
    svc = _patch_nullpool_session(test_engine, monkeypatch)
    _seed_videos(test_engine)

    svc.infer_many_from_db("video", [1, 2])

    actual = _status_rows(test_engine, "video")
    assert actual == {
        (1, "metadata_extract"): ("done", None, {
            "duration": 30.0,
            "resolution": "1920x1080",
            "fps": 30.0,
            "codec": "h264",
        }),
        (1, "scene_detection"): ("done", None, {"scenes": 2}),
        (1, "scene_db_storage"): ("done", None, {"scenes": 2}),
        # Nur 1 von 2 Scenes hat ai_caption (truthy)
        (1, "ai_scene_caption"): ("done", None, {"captioned_scenes": 1}),
        # Video 2: duration fehlt -> kein metadata_extract; keine Scenes ->
        # keine Scene-Steps. Keine Rows.
    }


def test_b620_single_infer_parity_matches_bulk(test_engine, monkeypatch):
    """infer_from_db (einzeln) schreibt dieselben Rows wie infer_many_from_db."""
    svc = _patch_nullpool_session(test_engine, monkeypatch)
    _seed_full_audio(test_engine)

    svc.infer_from_db("audio", 1)
    single = _status_rows(test_engine, "audio")

    # Frische DB, gleiche Fixture, Bulk-Pfad
    with Session(test_engine) as session:
        session.query(AnalysisStatus).delete()
        session.commit()
        # key_detection/lufs_analysis Vorbelegung wiederherstellen
        session.add(AnalysisStatus(
            media_type="audio", media_id=1, step_key="lufs_analysis",
            status="error", error_message="boom",
        ))
        session.add(AnalysisStatus(
            media_type="audio", media_id=1, step_key="key_detection",
            status="done", value_summary={"key": "OLD", "confidence": 0.1},
        ))
        session.commit()

    svc.infer_many_from_db("audio", [1])
    bulk = _status_rows(test_engine, "audio")

    assert single == bulk


def test_b620_missing_media_writes_nothing(test_engine, monkeypatch):
    svc = _patch_nullpool_session(test_engine, monkeypatch)
    with Session(test_engine) as session:
        session.add(Project(id=1, name="P", path="."))
        session.commit()

    svc.infer_many_from_db("audio", [999])
    svc.infer_many_from_db("video", [999])
    svc.infer_from_db("audio", 999)
    svc.infer_from_db("video", 999)

    assert _status_rows(test_engine, "audio") == {}
    assert _status_rows(test_engine, "video") == {}
