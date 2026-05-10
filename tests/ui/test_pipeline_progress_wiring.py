"""B-288 / B-290 / B-291: progress-Slots muessen progress_bar.setValue rufen."""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _slot_body(file_rel: str, slot_name: str) -> str:
    src = (REPO / file_rel).read_text(encoding="utf-8")
    pat = rf"def {re.escape(slot_name)}\([^)]*\):\n(?P<body>(?:    .+\n|\n)+)"
    m = re.search(pat, src)
    assert m, f"Slot {slot_name} nicht gefunden in {file_rel}"
    return m.group("body")


def test_b288_video_pipeline_slot_writes_progress_bar():
    body = _slot_body("ui/controllers/video_analysis.py", "_on_pipeline_progress")
    assert "progress_bar.setValue" in body, (
        "B-288: _on_pipeline_progress ruft progress_bar.setValue nicht — Bar bleibt 0%."
    )


def test_b290_stems_slot_writes_progress_bar():
    body = _slot_body("ui/controllers/stems.py", "_on_stem_progress")
    assert "progress_bar.setValue" in body, (
        "B-290: _on_stem_progress ruft progress_bar.setValue nicht."
    )


def test_b291_waveform_slot_writes_progress_bar():
    body = _slot_body("ui/controllers/audio_analysis.py", "_on_waveform_progress")
    assert "progress_bar.setValue" in body, (
        "B-291: _on_waveform_progress ruft progress_bar.setValue nicht."
    )


def test_stems_uses_named_slot_not_lambda():
    """B-290 follow-up: das alte Lambda darf nicht mehr existieren."""
    src = (REPO / "ui/controllers/stems.py").read_text(encoding="utf-8")
    assert "self._on_stem_progress" in src, (
        "B-290: Stems verbinden den neuen Slot nicht — alte Lambda-Verdrahtung aktiv."
    )
