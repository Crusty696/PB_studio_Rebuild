"""B-687 Defekt 2: Ist ein Segment kuerzer als seine Crossfade-Dauer, klemmte
der alte Code nur den Offset auf 0.1, dekrementierte ``accumulated_duration``
aber um die volle xfade-Dauer -> Akkumulator negativ, Frozen-Frames, gestapelte
Segmente. Fix: xfade_dur auf min(xfade, seg_i, accumulated) clampen.

Geprueft wird der generierte ``-filter_complex``: keine xfade-Dauer darf laenger
sein als das eingehende Segment.
"""
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import services.export_service as es


def _seg(path, start, dur, xfade):
    return {
        "path": path, "start": start, "end": start + dur,
        "source_duration": dur, "crossfade": xfade,
        "brightness": 0.0, "contrast": 1.0,
    }


def _capture_filter_complex(tmp_path, monkeypatch, segs):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"x")  # Post-Existenz-Check bestehen lassen

    monkeypatch.setattr(es, "_run_ffmpeg", fake_run)
    monkeypatch.setattr(
        es, "_prepare_normalized_audio",
        lambda audio_path, temp_files, progress_cb, step, total_steps, cancel_check=None: (None, step),
    )
    out = tmp_path / "out.mp4"
    es._export_with_filtergraph(segs, None, str(out), 1920, 1080, 30, None, 5)
    cmd = captured["cmd"]
    fc = cmd[cmd.index("-filter_complex") + 1]
    return re.findall(
        r"xfade=transition=fade:duration=([0-9.]+):offset=([0-9.]+)", fc
    )


def test_xfade_duration_never_exceeds_incoming_segment(tmp_path, monkeypatch):
    # Mittleres Segment (0.5 s) ist kuerzer als der Crossfade-Cap (2.0 s).
    segs = [
        _seg("a.mp4", 0.0, 3.0, 2.0),
        _seg("b.mp4", 3.0, 0.5, 2.0),
        _seg("c.mp4", 3.5, 3.0, 2.0),
    ]
    xfades = _capture_filter_complex(tmp_path, monkeypatch, segs)
    assert len(xfades) == 2

    durs = [float(d) for d, _o in xfades]
    # xfade #1 blendet in Segment[1] (source_duration 0.5) -> darf 0.5 nicht ueberschreiten.
    assert durs[0] <= segs[1]["source_duration"] + 1e-6, (
        f"xfade#1 Dauer {durs[0]} > Segment 0.5s -> Frozen-Frames (B-687 D2)"
    )
    # xfade #2 blendet in Segment[2] (3.0).
    assert durs[1] <= segs[2]["source_duration"] + 1e-6


def test_offsets_do_not_collapse_to_floor(tmp_path, monkeypatch):
    """Mit dem Clamp bleibt der Akkumulator positiv -> Offsets kollabieren nicht
    alle auf den 0.1-Floor (Zeichen des negativen Akkumulators im Altcode)."""
    segs = [
        _seg("a.mp4", 0.0, 3.0, 2.0),
        _seg("b.mp4", 3.0, 0.5, 2.0),
        _seg("c.mp4", 3.5, 3.0, 2.0),
    ]
    xfades = _capture_filter_complex(tmp_path, monkeypatch, segs)
    offsets = [float(o) for _d, o in xfades]
    # Nicht beide Offsets auf dem 0.1-Floor gepinnt.
    assert not all(abs(o - 0.1) < 1e-6 for o in offsets), (
        f"Offsets kollabiert auf Floor {offsets} -> Akkumulator negativ (B-687 D2)"
    )
