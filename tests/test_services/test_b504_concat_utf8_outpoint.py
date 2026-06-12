"""B-504: Export-Concat — UTF-8-Encoding, outpoint-Trim, VFR/pix_fmt-Probe.

Deckt ab:
1. Concat-Liste wird UTF-8 geschrieben (Umlaut-Pfad round-trip, strikte
   UTF-8-Dekodierung der Rohbytes — cp1252-geschriebene Umlaute wuerden
   hier mit UnicodeDecodeError scheitern).
2. Konformer Clip ohne Source-Offset, Segment kuerzer als Quellclip →
   ``inpoint 0`` + ``outpoint <segmentdauer>`` statt nur ``duration``
   (duration trimmt im concat-Demuxer nicht).
3. Segment == volle Clipdauer → weiterhin nur ``duration``-Zeile.
4. ``_needs_preprocessing``: VFR-Indiz (avg_frame_rate != r_frame_rate)
   und abweichendes pix_fmt → True; unbekannte Werte konservativ → False.
"""
from __future__ import annotations

import pytest


CONFORM_INFO = {
    "width": 1920, "height": 1080, "fps": 30.0, "avg_fps": 30.0,
    "codec": "h264", "pix_fmt": "yuv420p", "duration": 10.0,
}


@pytest.fixture
def exp(monkeypatch):
    from services import export_service as exp
    exp.clear_probe_cache()
    # NVENC-Detection nicht antriggern (subprocess) — CPU-Pfad erzwingen.
    monkeypatch.setattr(exp, "_export_nvenc_available", False)
    yield exp
    exp.clear_probe_cache()


def _seed_probe(exp, path, **overrides):
    info = dict(CONFORM_INFO)
    info.update(overrides)
    with exp._probe_cache_lock:
        exp._probe_cache[str(path)] = info
    return info


def _make_segment(path, start, end, source_start=0.0, source_duration=None):
    return {
        "path": str(path),
        "start": start,
        "end": end,
        "crossfade": 0.0,
        "brightness": 0.0,
        "contrast": 1.0,
        "source_start": source_start,
        "source_duration": (
            source_duration if source_duration is not None else end - start
        ),
    }


def _run_concat_export(exp, monkeypatch, tmp_path, segments):
    """Fuehrt _export_optimized_concat mit gemocktem FFmpeg aus.

    Gibt die Rohbytes der generierten Concat-Liste zurueck (vor Cleanup
    im finally abgegriffen).
    """
    captured = {}

    def fake_run_ffmpeg(cmd, timeout=None, progress_cb=None,
                        total_duration=None, cancel_check=None):
        if "-f" in cmd and "concat" in cmd:
            concat_path = cmd[cmd.index("-i") + 1]
            with open(concat_path, "rb") as fh:
                captured["raw"] = fh.read()
            # Output-Datei anlegen, damit der Existenz-Check besteht
            with open(cmd[-1], "wb") as fh:
                fh.write(b"fake-output")

    monkeypatch.setattr(exp, "_run_ffmpeg", fake_run_ffmpeg)
    monkeypatch.setattr(
        exp, "_prepare_normalized_audio",
        lambda audio_path, temp_files, progress_cb, step, total_steps,
        cancel_check=None: (None, step),
    )

    output_path = tmp_path / "out.mp4"
    exp._export_optimized_concat(
        segments, None, output_path,
        "1920", "1080", 30.0, None, 10,
    )
    assert "raw" in captured, "Concat-FFmpeg-Lauf wurde nicht ausgefuehrt"
    return captured["raw"]


# ---------------------------------------------------------------------------
# 1+2: UTF-8 + outpoint
# ---------------------------------------------------------------------------

def test_concat_list_utf8_umlaut_path_roundtrip(exp, monkeypatch, tmp_path):
    clip = tmp_path / "clip_äöü_grüße.mp4"
    _seed_probe(exp, clip, duration=10.0)
    seg = _make_segment(clip, 0.0, 2.0)

    raw = _run_concat_export(exp, monkeypatch, tmp_path, [seg])

    # Strikte UTF-8-Dekodierung: cp1252-Bytes (0xE4 fuer 'ä') wuerden hier
    # UnicodeDecodeError werfen.
    text = raw.decode("utf-8")
    assert "clip_äöü_grüße.mp4" in text


def test_concat_outpoint_written_when_segment_shorter_than_clip(
        exp, monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    _seed_probe(exp, clip, duration=10.0)
    # Timeline-Segment 2 s, Quellclip 10 s → muss getrimmt werden
    seg = _make_segment(clip, 0.0, 2.0)

    text = _run_concat_export(exp, monkeypatch, tmp_path, [seg]).decode("utf-8")
    lines = text.splitlines()

    assert "inpoint 0.000" in lines
    assert "outpoint 2.000" in lines
    assert not any(line.startswith("duration") for line in lines), (
        "duration-Zeile trimmt nicht — bei kuerzerem Segment muss "
        "inpoint/outpoint geschrieben werden"
    )


def test_concat_duration_written_when_segment_covers_full_clip(
        exp, monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    _seed_probe(exp, clip, duration=10.0)
    seg = _make_segment(clip, 0.0, 10.0)

    text = _run_concat_export(exp, monkeypatch, tmp_path, [seg]).decode("utf-8")
    lines = text.splitlines()

    assert "duration 10.000" in lines
    assert not any(line.startswith("outpoint") for line in lines)


def test_concat_source_offset_branch_unchanged(exp, monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    _seed_probe(exp, clip, duration=10.0)
    seg = _make_segment(clip, 0.0, 2.0, source_start=3.0, source_duration=2.0)

    text = _run_concat_export(exp, monkeypatch, tmp_path, [seg]).decode("utf-8")
    lines = text.splitlines()

    assert "inpoint 3.000" in lines
    assert "outpoint 5.000" in lines


def test_concat_unknown_clip_duration_falls_back_to_duration_line(
        exp, monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    # Konservativ: Dauer unbekannt (0.0) → kein outpoint-Trim, altes Verhalten
    _seed_probe(exp, clip, duration=0.0)
    seg = _make_segment(clip, 0.0, 2.0)

    text = _run_concat_export(exp, monkeypatch, tmp_path, [seg]).decode("utf-8")
    lines = text.splitlines()

    assert "duration 2.000" in lines
    assert not any(line.startswith("outpoint") for line in lines)


# ---------------------------------------------------------------------------
# 3: _needs_preprocessing — VFR + pix_fmt
# ---------------------------------------------------------------------------

def test_needs_preprocessing_conform_clip_false(exp):
    _seed_probe(exp, "conform.mp4")
    assert exp._needs_preprocessing("conform.mp4", 1920, 1080, 30.0) is False


def test_needs_preprocessing_vfr_indication_true(exp):
    # avg_frame_rate weicht > 0.5 fps von r_frame_rate ab → VFR-Indiz
    _seed_probe(exp, "vfr.mp4", avg_fps=24.7)
    assert exp._needs_preprocessing("vfr.mp4", 1920, 1080, 30.0) is True


def test_needs_preprocessing_unknown_avg_fps_conservative_false(exp):
    # avg_frame_rate "0/0" (unbekannt) zaehlt NICHT als Abweichung
    _seed_probe(exp, "noavg.mp4", avg_fps=0.0)
    assert exp._needs_preprocessing("noavg.mp4", 1920, 1080, 30.0) is False


def test_needs_preprocessing_deviating_pix_fmt_true(exp):
    _seed_probe(exp, "p10.mp4", pix_fmt="yuv420p10le")
    assert exp._needs_preprocessing("p10.mp4", 1920, 1080, 30.0) is True


def test_needs_preprocessing_unknown_pix_fmt_conservative_false(exp):
    # pix_fmt unbekannt (leer) → konservativ keine Abweichung unterstellen
    _seed_probe(exp, "nopix.mp4", pix_fmt="")
    assert exp._needs_preprocessing("nopix.mp4", 1920, 1080, 30.0) is False


def test_needs_preprocessing_resolution_mismatch_still_true(exp):
    # Regression: bestehende Checks unveraendert
    _seed_probe(exp, "sd.mp4", width=1280, height=720)
    assert exp._needs_preprocessing("sd.mp4", 1920, 1080, 30.0) is True


def test_needs_preprocessing_empty_probe_true(exp):
    with exp._probe_cache_lock:
        exp._probe_cache["broken.mp4"] = {}
    assert exp._needs_preprocessing("broken.mp4", 1920, 1080, 30.0) is True


def test_parse_frame_rate_variants(exp):
    assert exp._parse_frame_rate("30/1") == 30.0
    assert exp._parse_frame_rate("30000/1001") == pytest.approx(29.97, abs=0.01)
    assert exp._parse_frame_rate("0/0") == 0.0
    assert exp._parse_frame_rate("N/A") == 0.0
    assert exp._parse_frame_rate("29.97") == pytest.approx(29.97)
