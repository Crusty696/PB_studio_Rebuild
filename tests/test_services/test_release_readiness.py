from __future__ import annotations

from pathlib import Path

from services.release_readiness import production_blockers


def test_missing_artifacts_and_proofs_block_release(tmp_path: Path) -> None:
    blockers = production_blockers(tmp_path)
    ids = {blocker.blocker_id for blocker in blockers}

    assert {"ART-001", "ART-002", "ART-003", "VM-001", "GUI-001"}.issubset(ids)


def test_random_markdown_pass_text_does_not_clear_release_proof(tmp_path: Path) -> None:
    synthesis = tmp_path / "docs" / "superpowers" / "synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / "clean-vm-install-random-pass.md").write_text(
        "# Clean VM Install\n\nPASS, but no release proof schema.\n",
        encoding="utf-8",
    )

    blockers = production_blockers(tmp_path)
    ids = {blocker.blocker_id for blocker in blockers}

    assert "VM-001" in ids


def test_schema_proof_clears_matching_release_proof_only(tmp_path: Path) -> None:
    synthesis = tmp_path / "docs" / "superpowers" / "synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / "clean-vm-install-live.md").write_text(
        "---\n"
        "release_gate_proof: true\n"
        "proof_type: clean-vm-install\n"
        "status: pass\n"
        "evidence_level: live\n"
        "---\n"
        "# Clean VM Install\n",
        encoding="utf-8",
    )

    blockers = production_blockers(tmp_path)
    ids = {blocker.blocker_id for blocker in blockers}

    assert "VM-001" not in ids
    assert "GUI-001" in ids


def test_schema_proof_allows_utf8_bom_frontmatter(tmp_path: Path) -> None:
    synthesis = tmp_path / "docs" / "superpowers" / "synthesis"
    synthesis.mkdir(parents=True)
    (synthesis / "clean-vm-install-live.md").write_text(
        "\ufeff---\n"
        "release_gate_proof: true\n"
        "proof_type: clean-vm-install\n"
        "status: pass\n"
        "evidence_level: live\n"
        "---\n"
        "# Clean VM Install\n",
        encoding="utf-8",
    )

    blockers = production_blockers(tmp_path)
    ids = {blocker.blocker_id for blocker in blockers}

    assert "VM-001" not in ids
