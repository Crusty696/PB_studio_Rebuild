"""B-707: gemischte cut+crossfade-Gruppe erzeugte einen Filtergraphen, in dem ein
concat-Knoten (Output-Timebase 1/1000000) direkt vor einem xfade-Knoten
(verlangt 1/fps) stand -> "timebase do not match" -> 0 Frames -> stiller
Hard-Cut-Fallback.

Fix: jeder concat-Knoten bekommt ,settb=1/{fps} angehaengt. xfade-Knoten bleiben
unveraendert; reine cut- oder reine xfade-Ketten sind unbetroffen.

Geprueft am generierten -filter_complex (ohne echtes ffmpeg).
"""
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import services.export_service as es


def _seg(path, start, dur, xfade):
    return {
        "path": path, "start": start, "end": start + dur,
        "source_duration": dur, "duration": 60.0, "source_start": 0.0,
        "crossfade": xfade, "brightness": 0.0, "contrast": 1.0,
    }


def _filter_complex(tmp_path, monkeypatch, segs, fps=30):
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        Path(cmd[-1]).write_bytes(b"x")

    monkeypatch.setattr(es, "_run_ffmpeg", fake_run)
    monkeypatch.setattr(
        es, "_prepare_normalized_audio",
        lambda audio_path, temp_files, progress_cb, step, total_steps, cancel_check=None: (None, step),
    )
    out = tmp_path / "out.mp4"
    es._export_with_filtergraph(segs, None, str(out), 1920, 1080, fps, None, 5)
    cmd = captured["cmd"]
    return cmd[cmd.index("-filter_complex") + 1]


def test_concat_nodes_get_settb(tmp_path, monkeypatch):
    # Gemischte Gruppe: cut, cut, xfade, cut (der Fehlerfall aus B-707).
    segs = [
        _seg("a.mp4", 0.0, 3.0, 0.0),
        _seg("b.mp4", 3.0, 3.0, 0.0),
        _seg("c.mp4", 6.0, 3.0, 1.0),  # crossfade
        _seg("d.mp4", 9.0, 3.0, 0.0),
    ]
    fc = _filter_complex(tmp_path, monkeypatch, segs, fps=30)

    n_concat = len(re.findall(r"concat=n=2:v=1:a=0", fc))
    n_settb = len(re.findall(r"concat=n=2:v=1:a=0,settb=1/30", fc))
    assert n_concat >= 1, "kein concat-Knoten im gemischten Fall?"
    assert n_settb == n_concat, (
        f"nicht jeder concat hat ,settb=1/fps ({n_settb}/{n_concat}) -> "
        f"timebase-mismatch, 0 Frames (B-707)"
    )


def test_pure_xfade_chain_has_no_settb(tmp_path, monkeypatch):
    segs = [
        _seg("a.mp4", 0.0, 3.0, 1.0),
        _seg("b.mp4", 3.0, 3.0, 1.0),
        _seg("c.mp4", 6.0, 3.0, 1.0),
    ]
    fc = _filter_complex(tmp_path, monkeypatch, segs, fps=30)
    assert "concat=n=2" not in fc, "reine xfade-Kette darf keinen concat-Knoten haben"
    assert "settb" not in fc, "reine xfade-Kette darf kein settb bekommen (Pfad unberuehrt)"


def test_pure_cut_chain_all_concat_get_settb(tmp_path, monkeypatch):
    segs = [
        _seg("a.mp4", 0.0, 3.0, 0.0),
        _seg("b.mp4", 3.0, 3.0, 0.0),
        _seg("c.mp4", 6.0, 3.0, 0.0),
    ]
    fc = _filter_complex(tmp_path, monkeypatch, segs, fps=25)
    n_concat = len(re.findall(r"concat=n=2:v=1:a=0", fc))
    n_settb = len(re.findall(r"concat=n=2:v=1:a=0,settb=1/25", fc))
    assert n_concat >= 2
    assert n_settb == n_concat, "auch reine cut-Kette: jeder concat braucht settb (fps-korrekt)"
