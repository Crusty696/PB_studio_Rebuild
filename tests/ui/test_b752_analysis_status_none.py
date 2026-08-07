"""B-752: checkpoint-skip summaries may contain honest None values."""

import pytest

from ui.widgets.analysis_status_panel import AnalysisStatusPanel


@pytest.mark.parametrize(
    ("summary", "expected"),
    [
        ({"bpm": None}, "—"),
        ({"lufs": None, "key": None, "confidence": None}, "—"),
        ({"bpm": None, "mood": "energetic", "genre": None}, "energetic"),
        ({"bpm": 128, "lufs": -9.25, "key": "8A"}, "128.0 BPM, Key: 8A, -9.2 LUFS"),
    ],
)
def test_b752_format_value_summary_handles_none_without_crash(
    summary: dict,
    expected: str,
) -> None:
    assert AnalysisStatusPanel._format_value_summary(None, summary) == expected
