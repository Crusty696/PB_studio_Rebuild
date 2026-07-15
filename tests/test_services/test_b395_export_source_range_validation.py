from __future__ import annotations

from types import SimpleNamespace

import pytest


class _Query:
    def __init__(self, rows):
        self._rows = rows

    def filter_by(self, **kwargs):
        return self

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Result:
    # B-090: Ergebnis-Wrapper fuer session.execute(select(...)). Der
    # Produktions-Code ruft darauf .all() (Clip-Bulk-Load) bzw. .first()
    # (Audio-Track) auf.
    def __init__(self, rows):
        self._rows = list(rows)

    def all(self):
        return list(self._rows)

    def first(self):
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, entries, clips):
        self._entries = entries
        self._clips = clips

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def query(self, model):
        from services import export_service as exp

        if model is exp.TimelineEntry:
            return _Query(self._entries)
        if model is exp.VideoClip:
            return _Query(self._clips)
        if model is exp.AudioTrack:
            return _Query([])
        raise AssertionError(f"unexpected query model {model!r}")

    def execute(self, stmt):
        # B-090: column-select-Support. Seit B-090 selektiert der Export
        # nur noch Skalar-Spalten via session.execute(select(VideoClip.id,
        # VideoClip.file_path, VideoClip.duration)).all() bzw.
        # select(AudioTrack.file_path, AudioTrack.duration).first(), um
        # eager JSON-Blob-Loads zu vermeiden. Diese Mock-Methode ermittelt
        # aus dem select-Statement die Ziel-Entity und liefert die bereits
        # gemockten Rows ueber die vorhandene query()-Mapping zurueck
        # (self.query() ist polymorph -> Subklassen-Override, z.B. fuer
        # AudioTrack, greift automatisch).
        model = self._model_from_stmt(stmt)
        return _Result(self.query(model).all())

    @staticmethod
    def _model_from_stmt(stmt):
        from services import export_service as exp

        # Bevorzugt: column_descriptions -> gemappte Entity der 1. Spalte.
        try:
            descs = stmt.column_descriptions
            if descs and descs[0].get("entity") is not None:
                return descs[0]["entity"]
        except Exception:
            pass
        # Fallback: 1. selektierte Spalte -> .table mit Model.__table__ vergl.
        table = None
        try:
            table = list(stmt.selected_columns)[0].table
        except Exception:
            table = None
        for model in (exp.VideoClip, exp.AudioTrack, exp.TimelineEntry):
            if table is not None and table is model.__table__:
                return model
        raise AssertionError(f"unexpected execute() statement {stmt!r}")


def test_b395_export_rejects_negative_source_duration_before_ffmpeg(tmp_path, monkeypatch):
    from services import export_service as exp

    entry = SimpleNamespace(
        id=10,
        project_id=1,
        track="video",
        media_id=7,
        start_time=0.0,
        end_time=2.0,
        source_start=5.0,
        source_end=3.0,
        crossfade_duration=0.0,
        brightness=0.0,
        contrast=1.0,
    )
    clip = SimpleNamespace(id=7, file_path="clip.mp4", duration=10.0)

    monkeypatch.setattr(exp, "_cleanup_orphan_tempfiles", lambda: 0)
    monkeypatch.setattr(exp, "clear_probe_cache", lambda: None)
    monkeypatch.setattr(exp, "_get_export_dir", lambda: tmp_path / "exports")
    monkeypatch.setattr(exp, "Session", lambda engine: _Session([entry], [clip]))
    monkeypatch.setattr(
        exp,
        "_export_optimized_concat",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("FFmpeg path reached")),
    )

    with pytest.raises(ValueError, match="source_duration"):
        exp.export_timeline(project_id=1, output_name="safe.mp4")

