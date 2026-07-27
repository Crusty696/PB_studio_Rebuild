"""B-720 — Guards fuer CI-/Release-Workflows und Release-Readiness-Pfade.

Diese Tests pruefen ausschliesslich statische Repo-Fakten (YAML/TOML/Dateisystem).
Sie starten nichts, laden keine Modelle und rufen kein Netzwerk.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
RELEASE_YML = WORKFLOWS / "release.yml"
AUTO_MERGE_YML = WORKFLOWS / "auto-merge.yml"
CI_YML = WORKFLOWS / "ci.yml"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _strip_comments(text: str) -> str:
    """Entfernt reine YAML-Kommentarzeilen und Trailing-Kommentare.

    Noetig, weil die Fixes ihre Begruendung als Kommentar im Workflow
    dokumentieren — ein naiver Substring-Check wuerde sonst den erklaerenden
    Kommentar als "aktive Konfiguration" missverstehen.
    """
    out = []
    for line in text.splitlines():
        stripped = line.split("#", 1)[0]
        if stripped.strip():
            out.append(stripped)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# B-720 Hauptbefund: release.yml Zielruntime
# ---------------------------------------------------------------------------


def test_release_workflow_uses_target_runtime_not_py311_cu124_poetry():
    active = _strip_comments(_read(RELEASE_YML))

    assert 'python-version: "3.10"' in active, "release.yml muss die Zielruntime Python 3.10 setzen"
    assert 'python-version: "3.11"' not in active, "release.yml darf nicht mehr auf Python 3.11 bauen"
    assert "requirements-py310-cu113.txt" in active, (
        "release.yml muss die kanonische Pin-Datei requirements-py310-cu113.txt installieren"
    )
    assert "cu124" not in active, "release.yml darf keinen cu124-Torch-Index mehr benutzen (GPU-Hartregel: cu113)"
    assert "poetry install" not in active, (
        "poetry.lock ist gegenueber pyproject.toml veraltet — poetry install darf nicht der Install-Pfad sein"
    )


# ---------------------------------------------------------------------------
# B-720: release.yml ist deaktiviert + Grund dokumentiert
# ---------------------------------------------------------------------------


def test_release_workflow_has_no_automatic_tag_trigger():
    active = _strip_comments(_read(RELEASE_YML))

    # Der Tag-Trigger stand als `tags:` / `- "v*.*.*"` unter `on: push:`.
    assert not re.search(r"^\s*tags:\s*$", active, re.MULTILINE), (
        "release.yml darf nicht mehr automatisch auf Tag-Push starten (B-720)"
    )
    assert "workflow_dispatch:" in active, "manueller Notausgang soll erhalten bleiben"


def test_release_workflow_documents_why_it_is_deactivated():
    text = _read(RELEASE_YML)

    assert "B-720" in text
    assert "bin/ffmpeg.exe" in text, "Grund (gitignored FFmpeg-Binaries) muss im Workflow stehen"
    assert "gitignore" in text.lower()


def test_release_workflow_fails_fast_when_ffmpeg_binaries_are_missing():
    active = _strip_comments(_read(RELEASE_YML))

    assert "Preflight" in active, "release.yml braucht einen Preflight-Step fuer die FFmpeg-Binaries"
    assert "bin/$name" in active or "bin/ffmpeg.exe" in active
    assert "exit 1" in active, "Preflight muss hart abbrechen, nicht nur warnen"


def test_ffmpeg_preflight_reflects_repo_reality_bin_is_gitignored():
    """Gegenprobe zur Randbedingung: bin/ ist wirklich ignoriert und leer."""
    gitignore = _read(ROOT / ".gitignore")
    assert re.search(r"^bin/\s*$", gitignore, re.MULTILINE), (
        "Annahme des Fixes gebrochen: bin/ ist nicht mehr gitignored"
    )


# ---------------------------------------------------------------------------
# B-720 Zusatz (Supply Chain): auto-merge.yml
# ---------------------------------------------------------------------------

_TRUSTED_ASSOCIATIONS = ("OWNER", "MEMBER", "COLLABORATOR")


def _job_condition_block(text: str, job_name: str) -> str:
    """Liefert den Text des Jobs von seiner Definition bis zu `steps:`."""
    match = re.search(rf"^  {re.escape(job_name)}:\s*$", text, re.MULTILINE)
    assert match, f"Job {job_name} nicht in auto-merge.yml gefunden"
    rest = text[match.end():]
    steps = re.search(r"^\s*steps:\s*$", rest, re.MULTILINE)
    return rest[: steps.start()] if steps else rest


@pytest.mark.parametrize("job_name", ["auto-merge", "cleanup-branches"])
def test_auto_merge_jobs_are_restricted_to_trusted_non_fork_prs(job_name: str):
    active = _strip_comments(_read(AUTO_MERGE_YML))
    block = _job_condition_block(active, job_name)

    assert "if:" in block, f"Job {job_name} laeuft ohne jede Bedingung (B-720: Auto-Merge fuer JEDEN PR)"
    assert "head.repo.full_name == github.repository" in block, (
        f"Job {job_name} braucht einen Fork-Filter"
    )
    assert "author_association" in block, f"Job {job_name} braucht einen Autor-Filter"
    for association in _TRUSTED_ASSOCIATIONS:
        assert association in block, f"Job {job_name}: erlaubte Association {association} fehlt"


def test_branch_cleanup_is_not_unconditional():
    active = _strip_comments(_read(AUTO_MERGE_YML))
    block = _job_condition_block(active, "cleanup-branches")

    assert "always()" not in block, (
        "cleanup-branches loeschte mit if: always() auch bei PR-losen status/check_suite-Events "
        "repo-weit Branches"
    )
    assert "github.event.pull_request != null" in block


# ---------------------------------------------------------------------------
# B-720 Zusatz: services/release_readiness.py Pfadliste
# ---------------------------------------------------------------------------


def test_release_relevant_paths_all_exist_in_repo():
    from services.release_readiness import _RELEASE_RELEVANT_PATHS

    missing = [path for path in _RELEASE_RELEVANT_PATHS if not (ROOT / path).exists()]
    assert not missing, (
        "ART-005/ART-006 filtern git status/git log ueber diese Pathspecs. "
        f"Nicht existierende Pfade sind wirkungslos: {missing}"
    )


def test_release_relevant_paths_cover_the_active_dependency_pin_file():
    from services.release_readiness import _RELEASE_RELEVANT_PATHS

    assert "requirements-py310-cu113.txt" in _RELEASE_RELEVANT_PATHS, (
        "Die real installierte Pin-Datei muss ART-005/ART-006 ausloesen koennen"
    )


# ---------------------------------------------------------------------------
# B-720 Zusatz: Marker-Deklaration vs. Realitaet
# ---------------------------------------------------------------------------

_UNUSED_TAG = "[UNUSED]"


def _declared_markers() -> dict[str, str]:
    """markers-Liste aus pyproject.toml lesen.

    Bewusst per Regex statt tomllib: tomllib gibt es erst ab Python 3.11,
    Zielruntime ist 3.10.
    """
    text = _read(ROOT / "pyproject.toml")
    block = re.search(r"^markers = \[(.*?)^\]", text, re.MULTILINE | re.DOTALL)
    assert block, "markers-Liste in pyproject.toml nicht gefunden"
    entries = re.findall(r'"([^"]+)"', block.group(1))
    assert entries, "markers-Liste ist leer"
    return {entry.split(":", 1)[0].strip(): entry for entry in entries}


def _markers_used_in_tests() -> set[str]:
    used: set[str] = set()
    for path in (ROOT / "tests").rglob("*.py"):
        if path.name == Path(__file__).name:
            continue
        for name in re.findall(r"pytest\.mark\.([A-Za-z_][A-Za-z0-9_]*)", path.read_text(encoding="utf-8", errors="replace")):
            used.add(name)
    return used


def test_declared_markers_match_actual_usage():
    declared = _declared_markers()
    used = _markers_used_in_tests()

    actually_unused = {name for name in declared if name not in used}
    annotated_unused = {name for name, entry in declared.items() if _UNUSED_TAG in entry}

    missing_annotation = sorted(actually_unused - annotated_unused)
    stale_annotation = sorted(annotated_unused - actually_unused)

    assert not missing_annotation, (
        f"Marker ohne einen einzigen Verwender, aber ohne {_UNUSED_TAG}-Vermerk: {missing_annotation}. "
        "Entweder Marker an Tests setzen oder in pyproject.toml ehrlich als unbenutzt kennzeichnen."
    )
    assert not stale_annotation, (
        f"Marker als {_UNUSED_TAG} deklariert, wird aber benutzt: {stale_annotation}"
    )


def test_ci_gate_only_names_declared_markers():
    gate = re.search(r'pytest -m "([^"]+)"', _read(CI_YML))
    assert gate, "CI-Gate nicht gefunden"

    gate_markers = set(re.findall(r"not\s+([A-Za-z_][A-Za-z0-9_]*)", gate.group(1)))
    declared = set(_declared_markers())

    assert gate_markers <= declared, f"CI-Gate nennt undeklarierte Marker: {sorted(gate_markers - declared)}"


def test_ci_documents_which_gate_markers_are_currently_noops():
    declared = _declared_markers()
    ci_text = _read(CI_YML)

    gate = re.search(r'pytest -m "([^"]+)"', ci_text)
    assert gate
    gate_markers = set(re.findall(r"not\s+([A-Za-z_][A-Za-z0-9_]*)", gate.group(1)))
    noop_gate_markers = {name for name in gate_markers if _UNUSED_TAG in declared.get(name, "")}

    if not noop_gate_markers:
        pytest.skip("kein Gate-Marker ist derzeit ein No-op")

    assert "no-op" in ci_text, "ci.yml muss benennen, dass Teile des Gates nichts ausschliessen"
    for name in sorted(noop_gate_markers):
        assert re.search(rf"`{re.escape(name)}`", ci_text), (
            f"ci.yml erwaehnt den no-op-Marker `{name}` nicht"
        )
