from __future__ import annotations

from pathlib import Path


def test_phase6_example_migration_template_exists_outside_runtime_scopes():
    root = Path("services/brain/storage/sql_migrations")
    template = root / "_templates" / "002_example_add_nullable_column.sql"

    assert template.exists()
    text = template.read_text(encoding="utf-8")
    assert "Do not copy BEGIN/COMMIT" in text
    assert "PRAGMA user_version" not in text
    assert "ALTER TABLE" in text


def test_runtime_migration_scopes_do_not_contain_placeholder_templates():
    root = Path("services/brain/storage/sql_migrations")
    runtime_scopes = [
        p for p in root.iterdir()
        if p.is_dir() and not p.name.startswith("_")
    ]

    assert runtime_scopes
    for scope in runtime_scopes:
        for sql_path in scope.glob("*.sql"):
            text = sql_path.read_text(encoding="utf-8").lower()
            assert "template only" not in text
            assert "example migration" not in text
