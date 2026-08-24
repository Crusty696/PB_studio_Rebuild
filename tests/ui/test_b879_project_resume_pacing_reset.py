"""B-879: Projektwechsel darf keinen Cut-Worker ueber Kurvenreset starten."""

from __future__ import annotations

import ast
import inspect
import textwrap


def test_project_switch_blocks_curve_changed_during_pacing_reset() -> None:
    from ui.controllers.project_management import ProjectManagementController

    source = textwrap.dedent(
        inspect.getsource(ProjectManagementController._on_project_changed)
    )
    tree = ast.parse(source)

    guarded_reset_found = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        blocks_pacing_curve = any(
            isinstance(item.context_expr, ast.Call)
            and isinstance(item.context_expr.func, ast.Name)
            and item.context_expr.func.id == "QSignalBlocker"
            and item.context_expr.args
            and isinstance(item.context_expr.args[0], ast.Name)
            and item.context_expr.args[0].id == "pacing_curve"
            for item in node.items
        )
        resets_curve = any(
            isinstance(child, ast.Call)
            and isinstance(child.func, ast.Attribute)
            and child.func.attr == "reset_curve"
            for statement in node.body
            for child in ast.walk(statement)
        )
        guarded_reset_found |= blocks_pacing_curve and resets_curve

    assert guarded_reset_found, (
        "B-879: administrativer Kurvenreset muss curve_changed blockieren; "
        "sonst startet Auto-Resume parallel einen Cut-Worker."
    )
