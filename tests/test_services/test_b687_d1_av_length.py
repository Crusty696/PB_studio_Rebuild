"""B-687 Defekt 1 (Variant A): Overlap-Extension gegen A/V-Drift.

Jedes Segment spielt beim Export um den Overlap-Tail laenger, damit die
xfade-Kette Material bekommt und die Composite-Gesamtdauer = Sigma(slot) =
Audiodauer bleibt (kein progressiver A/V-Drift). Der xfade-Offset landet dabei
exakt auf der Beat-Grenze (offset_i == start[i]).

Geprueft am generierten ffmpeg-Kommando (``-t``-Args + ``-filter_complex``),
ohne echtes ffmpeg (``_run_ffmpeg`` gemockt).
"""
import os
import re

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import services.export_service as es


def _seg(path, start, dur, xfade, clip_duration=60.0, source_start=0.0):
    return {
        "path": path, "start": start, "end": start + dur,
        "source_duration": dur, "duration": clip_duration,
        "source_start": source_start, "crossfade": xfade,
        "brightness": 0.0, "contrast": 1.0,
    }


def _build_cmd(tmp_path, monkeypatch, segs):
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
    es._export_with_filtergraph(segs, None, str(out), 1920, 1080, 30, None, 5)
    return captured["cmd"]


def _t_values(cmd):
    return [float(cmd[i + 1]) for i, tok in enumerate(cmd) if tok == "-t"]


def _xfades(cmd):
    fc = cmd[cmd.index("-filter_complex") + 1]
    return [
        (float(d), float(o))
        for d, o in re.findall(
            r"xfade=transition=fade:duration=([0-9.]+):offset=([0-9.]+)", fc
        )
    ]


def test_composite_length_equals_sum_of_slots_and_offsets_on_beat(tmp_path, monkeypatch):
    # 3 Slots a 2.0 s, back-to-back (start 0/2/4), Crossfade 1.0, viel Tail-Material.
    segs = [
        _seg("a.mp4", 0.0, 2.0, 1.0),
        _seg("b.mp4", 2.0, 2.0, 1.0),
        _seg("c.mp4", 4.0, 2.0, 1.0),
    ]
    slot_sum = sum(s["end"] - s["start"] for s in segs)  # 6.0

    cmd = _build_cmd(tmp_path, monkeypatch, segs)
    ts = _t_values(cmd)
    xfades = _xfades(cmd)

    # Composite = Sigma(-t) - Sigma(xfade) muss der Slot-Summe (= Audiodauer) entsprechen.
    composite = sum(ts) - sum(d for d, _o in xfades)
    assert abs(composite - slot_sum) < 1e-6, (
        f"Composite {composite} != Slot-Summe {slot_sum} -> A/V-Drift (B-687 D1)"
    )

    # Offsets beat-verankert: offset_i == start des eingehenden Segments.
    offsets = [o for _d, o in xfades]
    assert offsets == [2.0, 4.0], f"Offsets nicht beat-verankert: {offsets}"


def test_missing_tail_material_falls_back_to_hard_cut(tmp_path, monkeypatch):
    # Segment 0 hat KEIN Restmaterial (source_start+source_duration == clip.duration)
    # -> ext[0] == 0 -> Uebergang 0->1 muss harter Schnitt sein (kein xfade),
    #    kein Over-Read (-t[0] <= clip.duration - source_start).
    segs = [
        _seg("a.mp4", 0.0, 2.0, 1.0, clip_duration=2.0, source_start=0.0),  # kein Tail
        _seg("b.mp4", 2.0, 2.0, 1.0, clip_duration=60.0),
        _seg("c.mp4", 4.0, 2.0, 1.0, clip_duration=60.0),
    ]
    cmd = _build_cmd(tmp_path, monkeypatch, segs)
    ts = _t_values(cmd)
    xfades = _xfades(cmd)

    # Kein Over-Read auf dem material-losen Clip.
    assert ts[0] <= 2.0 + 1e-6, f"-t[0]={ts[0]} liest ueber clip.duration=2.0 hinaus"
    # Uebergang 0->1 ist hart -> nur EIN Crossfade (1->2) statt zwei.
    assert len(xfades) == 1, f"Erwartet 1 Crossfade (0->1 hart), bekam {len(xfades)}"
