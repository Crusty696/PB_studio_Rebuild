from __future__ import annotations

import ast
import importlib
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CANONICAL_RELEASE_API = (
    "https://api.github.com/repos/Crusty696/PB_studio_Rebuild/releases/latest"
)


def test_b901_version_check_is_enabled_in_default_app_path() -> None:
    tree = ast.parse((REPO_ROOT / "main.py").read_text(encoding="utf-8"))
    assignments = [
        node
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "ENABLE_VERSION_CHECK"
            for target in node.targets
        )
    ]

    assert len(assignments) == 1
    assert isinstance(assignments[0].value, ast.Constant)
    assert assignments[0].value.value is True


def test_b901_version_check_uses_canonical_repo_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PBSTUDIO_UPDATE_API_URL", raising=False)
    import services.version_check_service as version_check_service

    version_check_service = importlib.reload(version_check_service)

    assert version_check_service._DEFAULT_API_URL == CANONICAL_RELEASE_API
