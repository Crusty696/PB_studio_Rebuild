import pytest
from unittest.mock import MagicMock, patch
from database import nullpool_session, Project, AudioTrack, WaveformData
from workers.audio_pipeline_v2_worker import AudioPipelineV2Worker
from services.analysis_status_service import get_status
from services.audio_pipeline.stages import DEFAULT_STAGE_ORDER, ClassifyStage, WaveformStage

def test_a2_stage_order_contains_new_stages():
    """Prüft, ob DEFAULT_STAGE_ORDER die Stages ClassifyStage und WaveformStage enthält."""
    assert ClassifyStage in DEFAULT_STAGE_ORDER
    assert WaveformStage in DEFAULT_STAGE_ORDER

def test_audio_pipeline_v2_worker_a2_full_run():
    """Testet den V2-Worker-Lauf mit gemockten Stages, um DB-Persistierung und Status-Writes zu verifizieren."""
    # 1. DB Setup: Ein temporäres Projekt und Track anlegen
    from database.migrations import init_db
    init_db()
    
    with nullpool_session() as session:
        proj = Project(name="Test A2 Project", path=".", resolution="1920x1080", fps=30.0)
        session.add(proj)
        session.commit()
        proj_id = proj.id
        
        track = AudioTrack(project_id=proj_id, file_path="dummy_a2.mp3", duration=120.0)
        session.add(track)
        session.commit()
        track_id = track.id
        
    # Vorab-Cleanup von eventuell vorhandenen Checkpoint-Dateien für diesen Track
    from services.audio_pipeline import stem_cache
    try:
        stem_cache.cache_meta_path(track_id).unlink(missing_ok=True)
    except Exception:
        pass
        
    try:
        # Mock-Stages für alle 10 default Stages erstellen
        mock_stages = []
        for stage_cls in DEFAULT_STAGE_ORDER:
            stage_name = stage_cls.name
            mock_stage = MagicMock()
            mock_stage.name = stage_name
            
            # Verhalten je nach Stage-Name definieren
            def make_run(name=stage_name):
                def _run(ctx):
                    if name == "beat_grid":
                        ctx.set_result(name, {"bpm": 124.0})
                    elif name == "key":
                        ctx.set_result(name, {"key": "Am", "confidence": 0.9})
                    elif name == "lufs":
                        ctx.set_result(name, {"integrated_lufs": -14.0})
                    elif name == "classify":
                        # Simuliere Classify-Result
                        from services.audio_classify_service import ClassifyResult
                        res = ClassifyResult(
                            mood="euphoric",
                            genre="Psytrance",
                            energy_level="high",
                            is_dj_mix=True,
                            confidence=0.85,
                            description="Test description",
                            sub_genre="Progressive Psytrance"
                        )
                        # persistiert in DB und setzt result im context
                        fields = {
                            "mood": res.mood,
                            "genre": res.genre,
                            "sub_genre": res.sub_genre,
                            "is_dj_mix": res.is_dj_mix,
                        }
                        from services.audio_pipeline.stages import _persist_to_track
                        _persist_to_track(ctx.track_id, fields)
                        ctx.set_result(name, {
                            "mood": res.mood,
                            "genre": res.genre,
                            "sub_genre": res.sub_genre,
                            "is_dj_mix": res.is_dj_mix,
                            "confidence": res.confidence,
                        })
                    elif name == "waveform":
                        # In DB persistieren
                        from database import WaveformData
                        with nullpool_session() as sess:
                            # DB-07 Fix: query check
                            existing = sess.query(WaveformData).filter_by(audio_track_id=ctx.track_id).first()
                            if not existing:
                                wd = WaveformData(
                                    audio_track_id=ctx.track_id,
                                    num_samples=2000,
                                    duration=120.0,
                                    band_low=[0.1]*2000,
                                    band_mid=[0.2]*2000,
                                    band_high=[0.3]*2000
                                )
                                sess.add(wd)
                                sess.commit()
                        ctx.set_result(name, {
                            "num_samples": 2000,
                            "duration": 120.0,
                        })
                    else:
                        ctx.set_result(name, {})
                return _run
                
            mock_stage.run = make_run()
            mock_stages.append(mock_stage)
            
        with patch("services.audio_pipeline.stages.build_default_stages", return_value=mock_stages):
            worker = AudioPipelineV2Worker(audio_track_id=track_id, file_path="dummy_a2.mp3")
            finished_called = []
            worker.finished.connect(lambda tid, res: finished_called.append((tid, res)))
            
            # Ausführen
            worker.run()
            
            # Verify finished signal
            assert len(finished_called) == 1
            
        # 2. Assertions auf DB-Felder am AudioTrack
        with nullpool_session() as session:
            db_track = session.get(AudioTrack, track_id)
            assert db_track.mood == "euphoric"
            assert db_track.genre == "Psytrance"
            assert db_track.sub_genre == "Progressive Psytrance"
            assert db_track.is_dj_mix is True
            
            # WaveformData prüfen
            wd = session.query(WaveformData).filter_by(audio_track_id=track_id).first()
            assert wd is not None
            assert wd.num_samples == 2000
            
        # 3. Assertions auf analysis_status
        status = get_status("audio", track_id)
        assert "bpm_detection" in status
        assert status["bpm_detection"].status == "done"
        assert status["bpm_detection"].value_summary.get("bpm") == 124.0
        
        assert "mood_genre_classify" in status
        assert status["mood_genre_classify"].status == "done"
        assert status["mood_genre_classify"].value_summary.get("mood") == "euphoric"
        assert status["mood_genre_classify"].value_summary.get("genre") == "Psytrance"
        assert status["mood_genre_classify"].value_summary.get("sub_genre") == "Progressive Psytrance"
        assert status["mood_genre_classify"].value_summary.get("is_dj_mix") is True
        
        assert "waveform_analysis" in status
        assert status["waveform_analysis"].status == "done"
        assert status["waveform_analysis"].value_summary.get("num_samples") == 2000
        
    finally:
        # Cleanup Checkpoint
        try:
            stem_cache.cache_meta_path(track_id).unlink(missing_ok=True)
        except Exception:
            pass
        # Cleanup DB
        with nullpool_session() as session:
            session.query(WaveformData).filter_by(audio_track_id=track_id).delete()
            session.query(AudioTrack).filter_by(id=track_id).delete()
            session.query(Project).filter_by(id=proj_id).delete()
            session.commit()
