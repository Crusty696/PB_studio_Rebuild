"""
Tests fuer services/pacing_memory.py

Getestet: learn_from_anchor(), record_rl_feedback(), _get_ai_memory_bias()
"""

import pytest
from sqlalchemy.orm import Session

import database
from database import AudioTrack, AIPacingMemory, Beatgrid, Scene, VideoClip


# ---------------------------------------------------------------------------
# learn_from_anchor() Tests
# ---------------------------------------------------------------------------

class TestLearnFromAnchor:
    """Tests fuer die learn_from_anchor() Funktion."""

    def test_learn_basic_anchor(self, test_engine, audio_track):
        """Speichert eine einfache Anker-Entscheidung."""
        from services.pacing_memory import learn_from_anchor

        result = learn_from_anchor(
            audio_track_id=audio_track.id,
            anchor_time=10.0,
            label="Test-Anker",
        )

        assert result is True

        # Verify DB entry
        with Session(test_engine) as s:
            mem = s.query(AIPacingMemory).first()
            assert mem is not None
            assert mem.audio_track_id == audio_track.id
            assert mem.audio_time == 10.0
            assert mem.label == "Test-Anker"
            assert mem.bpm == 128.0  # from audio_track fixture

    def test_learn_with_energy_data(self, test_engine, audio_track, db_session):
        """Liest Energie-Daten aus Beatgrid und leitet Stimmung ab."""
        from services.pacing_memory import learn_from_anchor

        # Beatgrid mit Energie-Daten anlegen
        beats = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
        energy = [0.2, 0.3, 0.8, 0.9, 0.6, 0.4, 0.1]
        bg = Beatgrid(
            audio_track_id=audio_track.id,
            bpm=128.0,
            beat_positions=beats,
            energy_per_beat=energy,
        )
        db_session.add(bg)
        db_session.commit()

        result = learn_from_anchor(
            audio_track_id=audio_track.id,
            anchor_time=1.0,  # Index 2 → energy 0.8 → mood "drop"
        )

        assert result is True

        with Session(test_engine) as s:
            mem = s.query(AIPacingMemory).first()
            assert mem.overall_energy == pytest.approx(0.8)
            assert mem.mood == "drop"
            assert mem.cut_type == "hard_cut"  # energy > 0.65

    def test_learn_low_energy_gives_crossfade(self, test_engine, audio_track, db_session):
        """Niedrige Energie → crossfade statt hard_cut."""
        from services.pacing_memory import learn_from_anchor

        beats = [0.0, 1.0, 2.0]
        energy = [0.1, 0.2, 0.15]
        bg = Beatgrid(
            audio_track_id=audio_track.id,
            bpm=128.0,
            beat_positions=beats,
            energy_per_beat=energy,
        )
        db_session.add(bg)
        db_session.commit()

        result = learn_from_anchor(
            audio_track_id=audio_track.id,
            anchor_time=1.0,
        )
        assert result is True

        with Session(test_engine) as s:
            mem = s.query(AIPacingMemory).first()
            assert mem.cut_type == "crossfade"
            assert mem.crossfade_duration == 1.5

    def test_learn_with_scene(self, test_engine, audio_track, video_clip, db_session):
        """Lernt mit Szenen-Kontext (RAFT motion)."""
        from services.pacing_memory import learn_from_anchor

        scene = Scene(
            video_clip_id=video_clip.id,
            start_time=0.0,
            end_time=5.0,
            energy=0.9,
        )
        db_session.add(scene)
        db_session.commit()
        db_session.refresh(scene)

        result = learn_from_anchor(
            audio_track_id=audio_track.id,
            anchor_time=2.5,
            scene_id=scene.id,
        )

        assert result is True

        with Session(test_engine) as s:
            mem = s.query(AIPacingMemory).first()
            assert mem.raft_motion == 0.9
            assert mem.scene_id == scene.id

    def test_learn_nonexistent_audio_track(self, test_engine):
        """Fehlende AudioTrack → return False."""
        from services.pacing_memory import learn_from_anchor

        result = learn_from_anchor(audio_track_id=99999, anchor_time=5.0)
        assert result is False

    def test_learn_nonexistent_scene(self, test_engine, audio_track):
        """Fehlende Scene → return False."""
        from services.pacing_memory import learn_from_anchor

        result = learn_from_anchor(
            audio_track_id=audio_track.id,
            anchor_time=5.0,
            scene_id=99999,
        )
        assert result is False

    def test_learn_default_label(self, test_engine, audio_track):
        """Ohne Label wird ein Default-Label generiert."""
        from services.pacing_memory import learn_from_anchor

        result = learn_from_anchor(
            audio_track_id=audio_track.id,
            anchor_time=42.5,
        )
        assert result is True

        with Session(test_engine) as s:
            mem = s.query(AIPacingMemory).first()
            assert "42.5" in mem.label  # "Anker@42.5s"

    def test_mood_mapping(self, test_engine, audio_track, db_session):
        """Testet verschiedene Energie-Stufen → Mood-Mapping."""
        from services.pacing_memory import learn_from_anchor

        # energy > 0.75 → "drop"
        # energy > 0.55 → "peak"
        # energy > 0.35 → "buildup"
        # energy > 0.2  → "breakdown"
        # else          → "warmup"
        test_cases = [
            (0.8, "drop"),
            (0.6, "peak"),
            (0.4, "buildup"),
            (0.25, "breakdown"),
            (0.1, "warmup"),
        ]

        for energy_val, expected_mood in test_cases:
            # Cleanup previous entries
            with Session(test_engine) as s:
                s.query(AIPacingMemory).delete()
                s.query(Beatgrid).filter_by(audio_track_id=audio_track.id).delete()
                s.commit()

            with Session(test_engine) as s:
                bg = Beatgrid(
                    audio_track_id=audio_track.id,
                    bpm=128.0,
                    beat_positions=[0.0, 1.0],
                    energy_per_beat=[energy_val, energy_val],
                )
                s.add(bg)
                s.commit()

            result = learn_from_anchor(
                audio_track_id=audio_track.id,
                anchor_time=0.5,
            )
            assert result is True

            with Session(test_engine) as s:
                mem = s.query(AIPacingMemory).first()
                assert mem.mood == expected_mood, (
                    f"energy={energy_val}: expected mood={expected_mood}, got {mem.mood}"
                )


# ---------------------------------------------------------------------------
# record_rl_feedback() Tests
# ---------------------------------------------------------------------------

class TestRecordRlFeedback:
    """Tests fuer record_rl_feedback()."""

    def test_positive_feedback(self, test_engine, audio_track, project):
        """Speichert positives RL-Feedback."""
        from services.pacing_memory import record_rl_feedback

        result = record_rl_feedback(
            audio_track_id=audio_track.id,
            sentiment="positive",
            project_id=project.id,
        )

        assert result is True

        with Session(test_engine) as s:
            mem = s.query(AIPacingMemory).first()
            assert mem is not None
            assert "positive" in mem.label
            assert mem.mood == "positive"
            assert mem.bpm == 128.0

    def test_negative_feedback(self, test_engine, audio_track, project):
        """Speichert negatives RL-Feedback."""
        from services.pacing_memory import record_rl_feedback

        result = record_rl_feedback(
            audio_track_id=audio_track.id,
            sentiment="negative",
            project_id=project.id,
        )

        assert result is True

        with Session(test_engine) as s:
            mem = s.query(AIPacingMemory).first()
            assert "negative" in mem.label

    def test_feedback_includes_clip_count(self, test_engine, audio_track, project):
        """cut_type enthaelt Clip-Anzahl."""
        from services.pacing_memory import record_rl_feedback

        result = record_rl_feedback(
            audio_track_id=audio_track.id,
            sentiment="positive",
            project_id=project.id,
        )
        assert result is True

        with Session(test_engine) as s:
            mem = s.query(AIPacingMemory).first()
            assert "feedback_" in mem.cut_type
            assert "_clips" in mem.cut_type


# ---------------------------------------------------------------------------
# _get_ai_memory_bias() Tests
# ---------------------------------------------------------------------------

class TestGetAiMemoryBias:
    """Tests fuer die Memory-Bias-Abfrage."""

    def test_no_memories_returns_none(self, test_engine):
        """Ohne gespeicherte Memories → None."""
        from services.pacing_memory import _get_ai_memory_bias
        import services.pacing_memory as pm
        pm.engine = test_engine

        result = _get_ai_memory_bias(bpm=128.0, overall_energy=0.5)
        assert result is None

    def test_similar_memory_returns_bias(self, test_engine, audio_track):
        """Aehnliche Memory wird als Bias zurueckgegeben."""
        from services.pacing_memory import _get_ai_memory_bias
        import services.pacing_memory as pm
        pm.engine = test_engine

        # Create a matching memory
        with Session(test_engine) as s:
            mem = AIPacingMemory(
                audio_track_id=audio_track.id,
                bpm=130.0,  # close to 128
                overall_energy=0.5,
                mood="peak",
                cut_type="hard_cut",
                crossfade_duration=0.0,
                raft_motion=0.7,
                label="Test Memory",
            )
            s.add(mem)
            s.commit()

        result = _get_ai_memory_bias(bpm=128.0, overall_energy=0.5)
        assert result is not None
        assert result["preferred_cut_type"] == "hard_cut"
        assert result["mood"] == "peak"
        assert result["preferred_motion"] == 0.7

    def test_dissimilar_memory_returns_none(self, test_engine, audio_track):
        """Zu unterschiedliche Memory → None."""
        from services.pacing_memory import _get_ai_memory_bias
        import services.pacing_memory as pm
        pm.engine = test_engine

        # Memory with very different BPM
        with Session(test_engine) as s:
            mem = AIPacingMemory(
                audio_track_id=audio_track.id,
                bpm=70.0,  # far from 128
                overall_energy=0.5,
                mood="warmup",
                cut_type="crossfade",
            )
            s.add(mem)
            s.commit()

        result = _get_ai_memory_bias(bpm=128.0, overall_energy=0.5)
        assert result is None

    def test_bias_picks_closest_match(self, test_engine, audio_track):
        """Bei mehreren Memories wird die aehnlichste gewaehlt."""
        from services.pacing_memory import _get_ai_memory_bias
        import services.pacing_memory as pm
        pm.engine = test_engine

        with Session(test_engine) as s:
            # Close match
            mem1 = AIPacingMemory(
                audio_track_id=audio_track.id,
                bpm=129.0,
                overall_energy=0.51,
                cut_type="hard_cut",
                label="Close Match",
            )
            # Less close match
            mem2 = AIPacingMemory(
                audio_track_id=audio_track.id,
                bpm=140.0,
                overall_energy=0.3,
                cut_type="crossfade",
                label="Far Match",
            )
            s.add_all([mem1, mem2])
            s.commit()

        result = _get_ai_memory_bias(bpm=128.0, overall_energy=0.5)
        assert result is not None
        assert result["label"] == "Close Match"
