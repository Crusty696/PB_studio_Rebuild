from __future__ import annotations

from pathlib import Path


def test_brain_v3_user_guide_covers_phase6_required_topics():
    path = Path("docs/user/brain_v3_user_guide.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8")

    required = [
        "Cold-Start",
        "Lern-Session",
        "Confidence-Balken",
        "Reset",
        "Backup",
    ]
    for needle in required:
        assert needle in text
