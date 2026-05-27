"""B-270 — EDL export missing opentimelineio-contrib (cmx_3600 adapter).

Im urspruenglichen Conda-Env (otio < 0.15, 2026-05-07) war der ``cmx_3600``-
Adapter nicht verfuegbar und ``TimelineService.export_edl`` crashte. In der
aktuellen Umgebung (opentimelineio 0.18.1) ist der Adapter mitgeliefert.

Dieser Test verankert das als Regression-Guard: faellt der Adapter wieder weg,
schlaegt der Test fehl (statt erst im Live-Export aufzufallen). Reiner
CPU-Test ohne GPU/FFmpeg.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import opentimelineio as otio


def test_b270_cmx3600_adapter_available() -> None:
    """Der cmx_3600-Adapter muss in der Umgebung registriert sein."""
    available = set(otio.adapters.available_adapter_names())
    assert "cmx_3600" in available, (
        "B-270: cmx_3600-EDL-Adapter fehlt — EDL-Export crasht. "
        f"Verfuegbar: {sorted(available)}"
    )


def test_b270_export_edl_writes_valid_edl(tmp_path) -> None:
    """TimelineService.export_edl erzeugt eine nicht-leere EDL-Datei."""
    from services.timeline_service import TimelineService

    ts = TimelineService(fps=30.0)
    ts.create_timeline("B270 EDL Smoke")
    track = ts.get_video_track(0)
    ts.add_clip(
        track=track,
        name="clip1",
        media_path="file:///tmp/clip1.mov",
        source_start=0.0,
        source_duration=2.0,
        available_duration=10.0,
    )

    out = tmp_path / "b270.edl"
    saved = ts.export_edl(out)

    saved_path = Path(saved)
    assert saved_path.exists(), "B-270: EDL-Datei wurde nicht geschrieben."
    assert saved_path.stat().st_size > 0, "B-270: EDL-Datei ist leer."
    text = saved_path.read_text(encoding="utf-8", errors="replace")
    assert "TITLE:" in text or "001" in text, (
        "B-270: EDL-Inhalt sieht nicht nach CMX-3600 aus:\n" + text[:200]
    )
