from __future__ import annotations

import os
from pathlib import Path

from services import release_readiness
from services.release_readiness import _RelevantCommit, production_blockers


def test_missing_artifacts_and_proofs_block_release(tmp_path: Path) -> None:
    blockers = production_blockers(tmp_path)
    ids = {blocker.blocker_id for blocker in blockers}

    assert {"ART-001", "ART-002", "ART-003", "VM-001", "GUI-001"}.issubset(ids)
    assert "SIGN-001" not in ids


def test_unsigned_installer_does_not_block_private_distribution(tmp_path: Path, monkeypatch) -> None:
    installer = tmp_path / "dist" / "pb_studio_setup_v0.5.0.exe"
    installer.parent.mkdir(parents=True)
    installer.write_bytes(b"installer")

    monkeypatch.setattr(release_readiness, "_authenticode_status", lambda _path: "NotSigned")

    blockers = production_blockers(tmp_path)
    ids = {blocker.blocker_id for blocker in blockers}

    assert "SIGN-001" not in ids


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


def test_stale_release_artifact_blocks_release(tmp_path: Path, monkeypatch) -> None:
    dist = tmp_path / "dist"
    frozen = dist / "pb_studio" / "pb_studio.exe"
    installer = dist / "pb_studio_setup_v0.5.0.exe"
    payload = dist / "pb_studio_setup_v0.5.0.nsisbin"
    for path in (frozen, installer, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")
    old_time = 1_700_000_000
    commit_time = old_time + 60
    for path in (frozen, installer, payload):
        path.touch()
        path.chmod(0o666)
        os.utime(path, (old_time, old_time))

    monkeypatch.setattr(release_readiness, "_authenticode_status", lambda _path: "Valid")
    monkeypatch.setattr(
        release_readiness,
        "_latest_release_relevant_commit",
        lambda _root: _RelevantCommit(
            commit_hash="abc123def4567890",
            timestamp=commit_time,
            iso_date="2026-07-03T13:43:45+02:00",
            subject="fix(B-553): ensure database-loaded waveforms have clip item as parent",
        ),
    )

    blockers = production_blockers(tmp_path)
    ids = {blocker.blocker_id for blocker in blockers}

    assert "ART-005" in ids


def test_fresh_release_artifact_does_not_block_release(tmp_path: Path, monkeypatch) -> None:
    dist = tmp_path / "dist"
    frozen = dist / "pb_studio" / "pb_studio.exe"
    installer = dist / "pb_studio_setup_v0.5.0.exe"
    payload = dist / "pb_studio_setup_v0.5.0.nsisbin"
    for path in (frozen, installer, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    monkeypatch.setattr(release_readiness, "_authenticode_status", lambda _path: "Valid")
    monkeypatch.setattr(
        release_readiness,
        "_latest_release_relevant_commit",
        lambda _root: _RelevantCommit(
            commit_hash="abc123def4567890",
            timestamp=1,
            iso_date="2026-07-03T13:43:45+02:00",
            subject="fix(B-553): ensure database-loaded waveforms have clip item as parent",
        ),
    )

    blockers = production_blockers(tmp_path)
    ids = {blocker.blocker_id for blocker in blockers}

    assert "ART-005" not in ids


def test_dirty_release_relevant_source_blocks_release(tmp_path: Path, monkeypatch) -> None:
    dist = tmp_path / "dist"
    frozen = dist / "pb_studio" / "pb_studio.exe"
    installer = dist / "pb_studio_setup_v0.5.0.exe"
    payload = dist / "pb_studio_setup_v0.5.0.nsisbin"
    for path in (frozen, installer, payload):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x")

    monkeypatch.setattr(
        release_readiness,
        "_latest_release_relevant_commit",
        lambda _root: _RelevantCommit(
            commit_hash="abc123def4567890",
            timestamp=1,
            iso_date="2026-07-03T13:43:45+02:00",
            subject="fix(B-553): ensure database-loaded waveforms have clip item as parent",
        ),
    )
    monkeypatch.setattr(
        release_readiness,
        "_release_relevant_dirty_paths",
        lambda _root: ["services/startup_checks.py", "services/pacing/scorer.py"],
    )

    blockers = production_blockers(tmp_path)
    ids = {blocker.blocker_id for blocker in blockers}

    assert "ART-006" in ids
