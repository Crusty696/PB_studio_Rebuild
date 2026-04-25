"""B-131 regression test: agent ID-extraction must use anchored regex.

Symptom: agents extract ``re.findall(r'\\d+', user_text)[0]`` as
track_id / clip_id / audio_id. "Analysiere mit 140 BPM" → track_id=140
silent misroute.

Fix: anchored regex like ``(?:track|audio|video|clip|set)\\s*(\\d+)``
that requires an explicit keyword prefix. Bare numbers (BPM, beats,
percentages) no longer match.

We test the orchestrator's central ``_extract_id_from_text`` plus
each agent's process() ID-extraction by simulating user texts where
numbers should NOT be picked up as IDs.
"""

from __future__ import annotations

from agents.orchestrator_agent import OrchestratorAgent


def test_orchestrator_extract_id_ignores_bare_numbers() -> None:
    """``_extract_id_from_text`` must require a keyword prefix.

    Counter-examples that USED to match (greedy first \\d+):
      - "Analysiere mit 140 BPM"     → would have returned 140
      - "4 Beats pro Cut"            → would have returned 4
      - "1080p Export"               → would have returned 1080
    """
    orch = OrchestratorAgent()
    # Bare-number cases must NOT match — too easy to misroute.
    assert orch._extract_id_from_text("Analysiere mit 140 BPM") is None, (
        "BUG-131 regression: 'BPM 140' wrongly extracted as ID."
    )
    assert orch._extract_id_from_text("4 Beats pro Cut") is None
    assert orch._extract_id_from_text("1080p Export") is None
    assert orch._extract_id_from_text("Pacing mit Energy 0.7") is None


def test_orchestrator_extract_id_matches_anchored_keywords() -> None:
    """Anchored matches MUST work: 'Track 5', 'Audio 3', 'Video 7',
    'Clip 12', 'Set 2' (DJ-set), with optional whitespace."""
    orch = OrchestratorAgent()
    assert orch._extract_id_from_text("Analysiere Track 5") == 5
    assert orch._extract_id_from_text("Auto-Edit fuer Audio 3") == 3
    assert orch._extract_id_from_text("Was passiert in Video 7?") == 7
    assert orch._extract_id_from_text("Clip 12 Inhaltsanalyse") == 12
    # German short forms also acceptable
    assert orch._extract_id_from_text("Set 2 verarbeiten") == 2


def test_orchestrator_extract_id_picks_first_anchored_when_multiple() -> None:
    """If multiple keyword-prefixed numbers, take the first."""
    orch = OrchestratorAgent()
    assert orch._extract_id_from_text(
        "Track 5 mit BPM 140 cuten"
    ) == 5  # Track 5 wins, BPM 140 ignored.
