from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LEGACY_HOME = Path(r"C:\Users\David Lochmann")
LEGACY_VAULT = Path(r"C:\Brain-Bug\projects\pb-studio")
CURRENT_VAULT = (
    Path.home() / "Documents" / "Vaults" / "Brain-Bug" / "projects" / "pb-studio"
)
REGISTRY = ROOT / "docs" / "superpowers" / "PLAN_REGISTRY.md"
ACTIVE_PLAN = ROOT / "docs" / "superpowers" / "ACTIVE_PLAN.md"


def _registry_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for line in REGISTRY.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) != 7:
            continue
        rows.append(
            {
                "plan_id": cells[0].strip("`"),
                "repo_path": cells[1].strip("`"),
                "vault_mirror": cells[2].strip("`"),
                "decision": cells[3].strip("`"),
                "status": cells[4].strip("`"),
                "next_allowed_task": cells[5],
                "blocker": cells[6],
            }
        )
    return rows


def _repo_path_exists(path_text: str) -> bool:
    if path_text.startswith("_sandbox_meta/"):
        return True
    path = Path(path_text)
    if (ROOT / path).exists():
        return True
    try:
        relative = path.relative_to(LEGACY_HOME)
    except (OSError, ValueError):
        return False
    return (Path.home() / relative).exists()


def _vault_path_exists(path_text: str) -> bool:
    path = Path(path_text)
    if path.exists():
        return True
    try:
        relative = path.relative_to(LEGACY_VAULT)
    except (OSError, ValueError):
        return False
    return (CURRENT_VAULT / relative).exists()


def test_agents_no_hardcoded_2026_05_14_plan_block() -> None:
    text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")

    assert "Authorized plan roots (as of 2026-05-14, active)" not in text
    assert "docs/superpowers/PLAN_REGISTRY.md" in text
    assert "docs/superpowers/ACTIVE_PLAN.md" in text


def test_registry_paths_exist_for_non_draft_plans() -> None:
    rows = _registry_rows()
    assert rows, "PLAN_REGISTRY.md must contain at least one plan row"

    for row in rows:
        assert _repo_path_exists(row["repo_path"]), row
        if row["status"] != "draft":
            assert _vault_path_exists(row["vault_mirror"]), row
            assert _vault_path_exists(row["decision"]), row


def test_active_plan_is_single_or_blocked() -> None:
    text = ACTIVE_PLAN.read_text(encoding="utf-8")
    status = re.search(r"^status:\s*(.+)$", text, re.MULTILINE)
    active = re.search(r"^active_plan_id:\s*(.+)$", text, re.MULTILINE)

    assert status is not None
    assert active is not None

    status_value = status.group(1).strip()
    active_value = active.group(1).strip()
    registry_ids = {row["plan_id"] for row in _registry_rows()}

    if status_value == "blocked-needs-user-selection":
        assert active_value == "none"
    else:
        assert status_value == "active"
        assert active_value in registry_ids
