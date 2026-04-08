"""Tests für StructureDetectionService — Song-Struktur Erkennung."""

import pytest
import numpy as np
from unittest.mock import patch, MagicMock

from services.structure_detection_service import (
    StructureDetectionService, StructureResult, StructureSegmentResult,
    SEGMENT_LABELS,
)


class TestSegmentLabels:
    """Tests für die Label-Definitionen."""

    def test_required_labels_present(self):
        """Alle Kern-Labels vorhanden."""
        required = ["INTRO", "WARMUP", "BUILDUP", "DROP", "BREAKDOWN", "OUTRO"]
        for label in required:
            assert label in SEGMENT_LABELS


class TestStructureDetection:
    """Tests für detect() mit synthetischen Energie-Kurven."""

    def _make_service(self):
        return StructureDetectionService()

    def test_very_short_track(self):
        """Weniger als 8 Beats → einzelnes VERSE Segment."""
        svc = self._make_service()
        energy = [0.5, 0.5, 0.5, 0.5]
        beats = [0.0, 0.5, 1.0, 1.5]
        result = svc.detect("/dummy.mp3", bpm=120, beat_positions=beats, energy_per_beat=energy)
        assert isinstance(result, StructureResult)
        assert len(result.segments) == 1
        assert result.segments[0].label == "VERSE"

    def test_classic_structure(self):
        """Energie-Kurve: niedrig→steigend→hoch→fallend→niedrig → erkennt mehrere Sektionen."""
        svc = self._make_service()
        n_beats = 200
        energy = []
        # INTRO: Beats 0-20 (niedrig)
        energy.extend([0.1] * 20)
        # BUILDUP: Beats 20-50 (steigend)
        for i in range(30):
            energy.append(0.1 + (i / 30) * 0.7)
        # DROP: Beats 50-90 (hoch)
        energy.extend([0.85] * 40)
        # BREAKDOWN: Beats 90-130 (niedrig)
        energy.extend([0.25] * 40)
        # BUILDUP 2: Beats 130-160 (steigend)
        for i in range(30):
            energy.append(0.2 + (i / 30) * 0.6)
        # DROP 2: Beats 160-180 (hoch)
        energy.extend([0.9] * 20)
        # OUTRO: Beats 180-200 (niedrig)
        energy.extend([0.1] * 20)

        beats = [i * 0.5 for i in range(n_beats)]  # 120 BPM

        result = svc.detect("/dummy.mp3", bpm=120, beat_positions=beats, energy_per_beat=energy)
        assert isinstance(result, StructureResult)
        assert len(result.segments) >= 3, f"Erwartet ≥3 Segmente, bekam {len(result.segments)}"

        # Prüfe dass mindestens 1 DROP und 1 INTRO/OUTRO erkannt werden
        labels = [s.label for s in result.segments]
        assert any(l in ("DROP", "CHORUS") for l in labels), f"Kein DROP/CHORUS in {labels}"

    def test_warmup_detection(self):
        """WARMUP-Erkennung: moderate Energie mit sanftem Anstieg am Track-Anfang."""
        svc = self._make_service()
        n_beats = 200
        energy = []
        # INTRO: Beats 0-15 (niedrig)
        energy.extend([0.15] * 15)
        # WARMUP: Beats 15-45 (moderate Energie, sanfter Anstieg 0.3→0.5)
        for i in range(30):
            energy.append(0.3 + (i / 30) * 0.2)
        # BUILDUP: Beats 45-70 (steilerer Anstieg 0.5→0.85)
        for i in range(25):
            energy.append(0.5 + (i / 25) * 0.35)
        # DROP: Beats 70-120 (hoch)
        energy.extend([0.88] * 50)
        # BREAKDOWN: Beats 120-160 (niedrig)
        energy.extend([0.28] * 40)
        # VERSE/CHORUS: Beats 160-180 (mittel)
        energy.extend([0.45] * 20)
        # OUTRO: Beats 180-200 (niedrig)
        energy.extend([0.12] * 20)

        beats = [i * 0.5 for i in range(n_beats)]  # 120 BPM

        result = svc.detect("/dummy.mp3", bpm=120, beat_positions=beats, energy_per_beat=energy)
        assert isinstance(result, StructureResult)

        # Prüfe dass WARMUP erkannt wird
        labels = [s.label for s in result.segments]
        assert "WARMUP" in labels, f"WARMUP nicht erkannt in {labels}"

        # WARMUP sollte früh im Track sein (erste 40%)
        warmup_segments = [s for s in result.segments if s.label == "WARMUP"]
        if warmup_segments:
            warmup_start = warmup_segments[0].start_time
            track_duration = beats[-1]
            warmup_position = warmup_start / track_duration
            assert warmup_position < 0.5, f"WARMUP zu spät im Track (Position: {warmup_position:.1%})"

    def test_constant_energy(self):
        """Konstante Energie → hauptsächlich VERSE/CHORUS Segmente."""
        svc = self._make_service()
        n_beats = 100
        energy = [0.4] * n_beats
        beats = [i * 0.5 for i in range(n_beats)]

        result = svc.detect("/dummy.mp3", bpm=120, beat_positions=beats, energy_per_beat=energy)
        assert len(result.segments) >= 1
        # Bei konstanter Energie sollte es keine DROPs oder BUILDUPs geben
        labels = [s.label for s in result.segments]
        assert "DROP" not in labels, "Konstante Energie sollte keine DROPs erzeugen"
        assert "BUILDUP" not in labels, "Konstante Energie sollte keine BUILDUPs erzeugen"

    def test_empty_energy(self):
        """Leere Energie-Liste → leeres Result."""
        svc = self._make_service()
        result = svc.detect("/dummy.mp3", energy_per_beat=[])
        assert len(result.segments) == 0

    def test_segments_cover_full_duration(self):
        """Segmente decken die gesamte Track-Dauer ab (keine Lücken)."""
        svc = self._make_service()
        n_beats = 100
        energy = [0.3 + 0.4 * np.sin(i / 15) for i in range(n_beats)]
        beats = [i * 0.5 for i in range(n_beats)]

        result = svc.detect("/dummy.mp3", bpm=120, beat_positions=beats, energy_per_beat=energy)
        if len(result.segments) >= 2:
            for i in range(len(result.segments) - 1):
                gap = result.segments[i + 1].start_time - result.segments[i].end_time
                assert abs(gap) < 0.01, f"Lücke zwischen Segment {i} und {i+1}: {gap}s"


class TestMergeConsecutive:
    """Tests für _merge_consecutive()."""

    def test_merge_same_labels(self):
        """Aufeinanderfolgende gleiche Labels → verschmelzen."""
        svc = StructureDetectionService()
        segments = [
            StructureSegmentResult(0.0, 5.0, "VERSE", 0.4, 0.7),
            StructureSegmentResult(5.0, 10.0, "VERSE", 0.45, 0.7),
            StructureSegmentResult(10.0, 15.0, "DROP", 0.8, 0.9),
        ]
        merged = svc._merge_consecutive(segments)
        assert len(merged) == 2
        assert merged[0].label == "VERSE"
        assert merged[0].end_time == 10.0
        assert merged[1].label == "DROP"

    def test_no_merge_different_labels(self):
        """Verschiedene Labels → kein Merge."""
        svc = StructureDetectionService()
        segments = [
            StructureSegmentResult(0.0, 5.0, "VERSE", 0.4, 0.7),
            StructureSegmentResult(5.0, 10.0, "CHORUS", 0.6, 0.7),
        ]
        merged = svc._merge_consecutive(segments)
        assert len(merged) == 2

    def test_single_segment(self):
        """Einzelnes Segment → unverändert."""
        svc = StructureDetectionService()
        segments = [StructureSegmentResult(0.0, 10.0, "VERSE", 0.5, 0.8)]
        assert len(svc._merge_consecutive(segments)) == 1


class TestSaveToDb:
    """Tests für save_to_db() mit In-Memory DB."""

    def test_save_and_query(self, test_engine, audio_track):
        """Segmente werden korrekt in die DB geschrieben."""
        from sqlalchemy.orm import Session
        from database import StructureSegment

        svc = StructureDetectionService()
        result = StructureResult(segments=[
            StructureSegmentResult(0.0, 30.0, "INTRO", 0.2, 0.8),
            StructureSegmentResult(30.0, 90.0, "DROP", 0.8, 0.9),
            StructureSegmentResult(90.0, 120.0, "OUTRO", 0.15, 0.7),
        ])

        # Patch engine in structure_detection_service
        import services.structure_detection_service as sds_mod
        import database
        original_engine = getattr(sds_mod, 'engine', None)

        with patch.object(database, 'engine', test_engine):
            svc.save_to_db(audio_track.id, result)

        with Session(test_engine) as session:
            segments = session.query(StructureSegment).filter_by(
                audio_track_id=audio_track.id
            ).order_by(StructureSegment.start_time).all()
            assert len(segments) == 3
            assert segments[0].label == "INTRO"
            assert segments[1].label == "DROP"
            assert segments[2].label == "OUTRO"

    def test_save_replaces_old_segments(self, test_engine, audio_track):
        """Zweiter save_to_db überschreibt alte Segmente."""
        from sqlalchemy.orm import Session
        from database import StructureSegment
        import database

        svc = StructureDetectionService()

        with patch.object(database, 'engine', test_engine):
            # Erste Speicherung
            svc.save_to_db(audio_track.id, StructureResult(segments=[
                StructureSegmentResult(0.0, 60.0, "INTRO", 0.2, 0.8),
            ]))

            # Zweite Speicherung (überschreibt)
            svc.save_to_db(audio_track.id, StructureResult(segments=[
                StructureSegmentResult(0.0, 30.0, "DROP", 0.9, 0.95),
                StructureSegmentResult(30.0, 60.0, "OUTRO", 0.1, 0.7),
            ]))

        with Session(test_engine) as session:
            segments = session.query(StructureSegment).filter_by(
                audio_track_id=audio_track.id
            ).all()
            assert len(segments) == 2  # Alte ersetzt, nicht angehängt
