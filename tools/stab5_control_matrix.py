"""Generate reproducible STAB-5 control-to-evidence matrix.

Static analysis only. It does not execute the application or tests and must
not be interpreted as live verification.
"""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/superpowers/synthesis/stab5-ui-control-matrix-2026-08-26.md"
CONTROL_TYPES = {
    "QPushButton",
    "QToolButton",
    "QAction",
    "QShortcut",
    "QCheckBox",
    "QComboBox",
}
FACTORIES = {
    ("ui/dialogs/setup_wizard.py", "_btn"): "QPushButton",
    ("ui/dialogs/setup_wizard.py", "_model_row"): "QCheckBox",
    ("ui/workspaces/media_workspace.py", "_toolbar_btn"): "QPushButton",
    ("ui/workspaces/schnitt/empty_view.py", "_make_preset_button"): "QPushButton",
    ("ui/workspaces/schnitt/timeline_shell.py", "_button"): "QPushButton",
}
MANUAL_BINDINGS = {
    ("ui/widgets/stem_mixer_panel.py", 91): (
        "ui/widgets/stem_workspace.py:145: track.solo_btn.toggled.connect(_on_solo_toggled)",
        "cross-file-exposed",
    ),
}


@dataclass
class Control:
    kind: str
    path: Path
    line: int
    context: str
    target: str
    label: str
    factory: str = ""
    binding: str = ""
    binding_scope: str = "unresolved"
    evidence: str = ""
    evidence_level: str = "no-candidate"


def dotted(node: ast.AST) -> str:
    try:
        return ast.unparse(node)
    except Exception:
        return "?"


def call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def literal_label(node: ast.Call) -> str:
    if not node.args:
        return ""
    arg = node.args[0]
    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
        return arg.value.replace("\n", " ")[:60]
    return dotted(arg)[:60]


def assigned_target(node: ast.Call, parents: dict[ast.AST, ast.AST]) -> str:
    parent = parents.get(node)
    if isinstance(parent, ast.Assign) and parent.value is node:
        return ", ".join(dotted(t) for t in parent.targets)
    if isinstance(parent, ast.AnnAssign) and parent.value is node:
        return dotted(parent.target)
    if isinstance(parent, ast.NamedExpr):
        return dotted(parent.target)
    return f"<inline@{node.lineno}>"


def enclosing_context(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    names: list[str] = []
    current = parents.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(current.name)
        current = parents.get(current)
    return ".".join(reversed(names)) or "<module>"


def enclosing_statement(node: ast.AST, parents: dict[ast.AST, ast.AST]) -> str:
    current: ast.AST | None = node
    while current is not None:
        if isinstance(current, ast.stmt):
            return dotted(current).replace("\n", " ")[:160]
        current = parents.get(current)
    return ""


def source_files() -> list[Path]:
    return [ROOT / "main.py", *sorted((ROOT / "ui").rglob("*.py"))]


def collect_controls() -> tuple[list[Control], dict[Path, str], int]:
    controls: list[Control] = []
    texts: dict[Path, str] = {}
    raw_constructor_sites = 0
    for path in source_files():
        text = path.read_text(encoding="utf-8")
        texts[path] = text
        tree = ast.parse(text, filename=str(path))
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            kind = call_name(node)
            relative = path.relative_to(ROOT)
            context = enclosing_context(node, parents)
            if kind in CONTROL_TYPES:
                raw_constructor_sites += 1
                if (relative.as_posix(), context.split(".")[-1]) in FACTORIES:
                    continue
                factory = ""
            else:
                factory_kind = FACTORIES.get((relative.as_posix(), kind))
                if factory_kind is None:
                    continue
                factory = kind
                kind = factory_kind
            if kind not in CONTROL_TYPES:
                continue
            control = Control(
                    kind=kind,
                    path=relative,
                    line=node.lineno,
                    context=context,
                    target=assigned_target(node, parents),
                    label=literal_label(node),
                    factory=factory,
                )
            statement = enclosing_statement(node, parents)
            if kind == "QShortcut" and len(node.args) >= 3:
                control.binding = f"constructor callback: {dotted(node.args[2])}"
                control.binding_scope = "local-constructor"
            elif ".connect(" in statement:
                control.binding = statement
                control.binding_scope = "local-inline"
            controls.append(control)
    return (
        sorted(controls, key=lambda c: (c.path.as_posix(), c.line, c.kind)),
        texts,
        raw_constructor_sites,
    )


def target_token(target: str) -> str:
    if target.startswith("<inline"):
        return ""
    pieces = re.findall(r"[A-Za-z_]\w*", target)
    return pieces[-1] if pieces else ""


def connection_lines(text: str, token: str) -> list[str]:
    if not token:
        return []
    token_pattern = re.compile(rf"\b{re.escape(token)}\b")
    found: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if token_pattern.search(line) and (".connect(" in line or ".addAction(" in line):
            found.append(line)
    return found


def consumer_lines(text: str, token: str) -> list[str]:
    if not token:
        return []
    token_pattern = re.compile(rf"\b{re.escape(token)}\b")
    markers = (
        ".currentText(",
        ".currentData(",
        ".currentIndex(",
        ".isChecked(",
        ".value(",
        ".setMenu(",
        ".exec(",
    )
    return [
        raw.strip()
        for raw in text.splitlines()
        if token_pattern.search(raw) and any(marker in raw for marker in markers)
    ]


def attach_bindings(controls: list[Control], texts: dict[Path, str]) -> None:
    repo_texts = {path.relative_to(ROOT): text for path, text in texts.items()}
    for control in controls:
        manual = MANUAL_BINDINGS.get((control.path.as_posix(), control.line))
        if manual:
            control.binding, control.binding_scope = manual
            continue
        if control.binding:
            continue
        token = target_token(control.target)
        local = connection_lines(repo_texts[control.path], token)
        if local:
            control.binding = local[0][:120]
            control.binding_scope = "local"
            continue
        local_consumers = consumer_lines(repo_texts[control.path], token)
        if local_consumers:
            control.binding = local_consumers[0][:120]
            control.binding_scope = "local-consumer"
            continue
        external: list[tuple[Path, str]] = []
        for path, text in repo_texts.items():
            if path == control.path:
                continue
            for line in connection_lines(text, token):
                external.append((path, line))
        if external:
            path, line = external[0]
            control.binding = f"{path.as_posix()}: {line}"[:160]
            control.binding_scope = "cross-file"
        else:
            external_consumers: list[tuple[Path, str]] = []
            for path, text in repo_texts.items():
                if path == control.path:
                    continue
                for line in consumer_lines(text, token):
                    external_consumers.append((path, line))
            if external_consumers:
                path, line = external_consumers[0]
                control.binding = f"{path.as_posix()}: {line}"[:160]
                control.binding_scope = "cross-file-consumer"
            else:
                control.binding = "indirekt/QMenu/noch manuell zuzuordnen"


def evidence_files() -> tuple[dict[Path, str], list[Path]]:
    tests = {
        path.relative_to(ROOT): path.read_text(encoding="utf-8", errors="replace")
        for path in sorted((ROOT / "tests" / "ui").rglob("*.py"))
        if path.name != "conftest.py"
    }
    syntheses = sorted((ROOT / "docs" / "superpowers" / "synthesis").glob("*.md"))
    return tests, syntheses


def attach_evidence(controls: list[Control]) -> None:
    tests, syntheses = evidence_files()
    synth_rel = [path.relative_to(ROOT) for path in syntheses]
    for control in controls:
        token = target_token(control.target)
        module = control.path.stem
        handler_tokens = re.findall(r"\b(?:self\.)?(_[A-Za-z_]\w*)", control.binding)
        candidates: list[tuple[int, Path]] = []
        for path, text in tests.items():
            score = 0
            path_text = path.as_posix()
            module_imported = module != "main" and bool(
                re.search(rf"(?:from|import)\s+[^\n]*\b{re.escape(module)}\b", text)
            )
            if module != "main" and (module in path.stem or module_imported):
                score += 4
            if token and len(token) >= 5 and re.search(rf"\b{re.escape(token)}\b", text):
                score += 3
            if any(re.search(rf"\b{re.escape(handler)}\b", text) for handler in handler_tokens):
                score += 2
            if score >= 4:
                candidates.append((score, path))
        candidates.sort(key=lambda item: (-item[0], item[1].as_posix()))
        if candidates:
            control.evidence = ", ".join(path.as_posix() for _, path in candidates[:2])
            control.evidence_level = "candidate-ref"
            continue
        synth_candidates = [path for path in synth_rel if module in path.name]
        if synth_candidates:
            control.evidence = synth_candidates[0].as_posix()
            control.evidence_level = "candidate-synthesis-ref"
        else:
            control.evidence = "kein elementgenauer Beleg automatisch gefunden"


def escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def render(controls: list[Control], raw_constructor_sites: int) -> str:
    kinds = Counter(control.kind for control in controls)
    scopes = Counter(control.binding_scope for control in controls)
    evidence = Counter(control.evidence_level for control in controls)
    lines = [
        "# STAB-5 elementgenaue UI-Control-Evidence-Matrix",
        "",
        "Datum: 2026-08-26",
        "Status: generated-static-matrix",
        "Generator: `tools/stab5_control_matrix.py`",
        "",
        "## Ergebnis",
        "",
        f"- Factory-expandierte sichtbare Deklarationsstellen: **{len(controls)}**.",
        "- Typen: " + ", ".join(f"{kind}={kinds[kind]}" for kind in sorted(kinds)) + ".",
        "- Bindung: " + ", ".join(f"{scope}={scopes[scope]}" for scope in sorted(scopes)) + ".",
        "- Evidenzreferenz: " + ", ".join(f"{level}={evidence[level]}" for level in sorted(evidence)) + ".",
        "",
        "Factory-Aufrufe sind expandiert; ein Call in einer Schleife bleibt eine",
        "Deklarationsstelle und kann mehrere Runtime-Widgets erzeugen. Die Zahl ist",
        "deshalb keine gemessene Runtime-Widgetanzahl.",
        "",
        "Statische Zuordnung. `candidate-ref` ist ausdrücklich kein Testbeleg:",
        "Test referenziert nur Modul, Control oder Handler. Read-only-Review fand",
        "zahlreiche Fehlzuordnungen. Kein aktueller Testlauf und kein Live-PASS.",
        "",
        "## Matrix",
        "",
        "| # | Typ | Source | Kontext | Control/Label | Signal/Handler | Scope | Belegkandidat | Stand |",
        "|---:|---|---|---|---|---|---|---|---|",
    ]
    for index, control in enumerate(controls, 1):
        identity = control.target
        if control.factory:
            identity += f" [factory:{control.factory}]"
        if control.label:
            identity += f" / {control.label}"
        lines.append(
            "| " + " | ".join(
                [
                    str(index),
                    control.kind,
                    f"`{control.path.as_posix()}:{control.line}`",
                    f"`{escape(control.context)}`",
                    f"`{escape(identity)}`",
                    f"`{escape(control.binding)}`",
                    control.binding_scope,
                    f"`{escape(control.evidence)}`",
                    control.evidence_level,
                ]
            ) + " |"
        )
    lines.extend(
        [
            "",
            "## Naechster Schritt",
            "",
            "Automatisch unresolved/indirekt gebundene Controls und reine",
            "`synthesis-ref`/`static-only`-Zeilen manuell pruefen. Danach nur echte",
            "Belegluecken gezielt am spaetestmoeglichen Endgate testen.",
            "",
            "## Methodikkorrektur",
            "",
            f"Veraltete fruehere Zahl: `{raw_constructor_sites}` rohe Constructor-Sites.",
            "Sie darf nicht als Control-, Fortschritts- oder Qualitaetswert benutzt werden.",
            "Factory-Expansion ergibt Deklarationsstellen, keine gemessene Runtime-Widgetzahl.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    controls, texts, raw_constructor_sites = collect_controls()
    attach_bindings(controls, texts)
    attach_evidence(controls)
    OUTPUT.write_text(render(controls, raw_constructor_sites), encoding="utf-8", newline="\n")
    print(
        f"raw_constructor_sites={raw_constructor_sites} "
        f"expanded_declarations={len(controls)} output={OUTPUT}"
    )
    return 0 if raw_constructor_sites == 182 else 2


if __name__ == "__main__":
    raise SystemExit(main())
