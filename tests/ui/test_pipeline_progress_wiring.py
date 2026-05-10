"""B-288 / B-290 / B-291: progress-Slots muessen progress_bar.setValue rufen."""
from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


def _slot_body(file_rel: str, slot_name: str) -> str:
    """Strikt an Funktions-Grenze endend — verhindert Over-Capture
    durch lockere Regex (Pre-Review Phase B 2026-05-10)."""
    import ast
    src = (REPO / file_rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == slot_name:
            seg = ast.get_source_segment(src, node)
            assert seg is not None, f"Source-Segment fuer {slot_name} leer."
            return seg
    raise AssertionError(f"Slot {slot_name} nicht gefunden in {file_rel}")


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


def test_audit_reproduction_grep_pipeline_wiring():
    """R-12 — Audit-Greps muessen Soll-Werte erreichen.

    Diese Greps belegen direkt dass keiner der urspruenglichen Symptom-
    Patterns zurueckgekehrt ist (B-287, B-288, B-289, B-290, B-291).
    """
    repo = REPO

    # B-287: metadata_extract muss in workers/video.py referenziert sein
    src_worker = (repo / "workers/video.py").read_text(encoding="utf-8")
    assert src_worker.count("metadata_extract") >= 1, (
        "B-287: workers/video.py referenziert metadata_extract nicht."
    )

    # B-289: progress.emit(100 muss in workers/video.py existieren
    assert "progress.emit(100" in src_worker, (
        "B-289: workers/video.py emittiert nie 100% — UI bleibt bei 99%."
    )

    # B-288/B-290/B-291: alle drei Slots haben setValue im Body (AST-strikt)
    for f, slot in [
        ("ui/controllers/video_analysis.py", "_on_pipeline_progress"),
        ("ui/controllers/stems.py", "_on_stem_progress"),
        ("ui/controllers/audio_analysis.py", "_on_waveform_progress"),
    ]:
        body = _slot_body(f, slot)
        assert "progress_bar.setValue" in body, (
            f"{f}::{slot} ruft progress_bar.setValue nicht — Slot ist tot."
        )
