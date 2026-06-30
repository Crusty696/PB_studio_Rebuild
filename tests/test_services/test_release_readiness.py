from __future__ import annotations

from pathlib import Path

from services.release_readiness import production_blockers


def test_missing_artifacts_and_proofs_block_release(tmp_path: Path) -> None:
    blockers = production_blockers(tmp_path)
    ids = {blocker.blocker_id for blocker in blockers}

    assert {"ART-001", "ART-002", "ART-003", "VM-001", "GUI-001"}.issubset(ids)
