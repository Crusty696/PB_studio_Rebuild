"""Coordinator for feeding project data into visible SCHNITT binders."""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from sqlalchemy.orm import Session

from database.models import AudioTrack, Beatgrid, StructureSegment, WaveformData

logger = logging.getLogger(__name__)


class SchnittCoordinator:
    """Loads SCHNITT UI data from DB and delegates rendering to binders."""

    def __init__(self, audio_binder, db_engine):
        self.audio_binder = audio_binder
        self.db_engine = db_engine

    def refresh_audio(self, audio_id: int | None) -> None:
        self.audio_binder.set_audio_id(audio_id)
        if audio_id is None:
            self.audio_binder.update_waveform(None, [], [])
            self.audio_binder.update_audio_meta(None, None, None)
            return

        with Session(self.db_engine) as session:
            track_row = (
                session.query(
                    AudioTrack.lufs,
                    AudioTrack.key,
                    AudioTrack.key_modulation_data,
                )
                .filter(AudioTrack.id == audio_id)
                .first()
            )
            if track_row is None:
                self.audio_binder.update_waveform(None, [], [])
                self.audio_binder.update_audio_meta(None, None, None)
                return

            waveform_row = (
                session.query(
                    WaveformData.audio_track_id,
                    WaveformData.num_samples,
                    WaveformData.duration,
                    WaveformData.band_low,
                    WaveformData.band_mid,
                    WaveformData.band_high,
                )
                .filter(WaveformData.audio_track_id == audio_id)
                .first()
            )
            waveform = None
            if waveform_row is not None:
                waveform = SimpleNamespace(
                    audio_track_id=waveform_row.audio_track_id,
                    num_samples=waveform_row.num_samples,
                    duration=waveform_row.duration,
                    band_low=waveform_row.band_low,
                    band_mid=waveform_row.band_mid,
                    band_high=waveform_row.band_high,
                )

            beatgrid_row = (
                session.query(Beatgrid.beat_positions)
                .filter(Beatgrid.audio_track_id == audio_id)
                .first()
            )
            segment_rows = (
                session.query(
                    StructureSegment.start_time,
                    StructureSegment.end_time,
                    StructureSegment.label,
                )
                .filter(StructureSegment.audio_track_id == audio_id)
                .order_by(StructureSegment.start_time)
                .all()
            )
            beat_positions = list(beatgrid_row.beat_positions or []) if beatgrid_row else []
            structure_markers = [
                {
                    "start": float(row.start_time),
                    "end": float(row.end_time),
                    "label": str(row.label),
                }
                for row in segment_rows
            ]
            self.audio_binder.update_waveform(waveform, beat_positions, structure_markers)
            self.audio_binder.update_audio_meta(
                track_row.lufs,
                track_row.key,
                self._camelot_from_values(track_row.key, track_row.key_modulation_data),
            )

    @staticmethod
    def _camelot_from_track(track: AudioTrack) -> str | None:
        return SchnittCoordinator._camelot_from_values(track.key, track.key_modulation_data)

    @staticmethod
    def _camelot_from_values(key: str | None, modulation_data: Any) -> str | None:
        if isinstance(modulation_data, list):
            for entry in modulation_data:
                if not isinstance(entry, dict):
                    continue
                if entry.get("key") == key and entry.get("camelot"):
                    return str(entry["camelot"])
            for entry in modulation_data:
                if isinstance(entry, dict) and entry.get("camelot"):
                    return str(entry["camelot"])
        return None
