# Phase 01 — DB Migrations

**Ziel:** Schema-Erweiterungen für Locking, Snapshots und Project-Notes.

---

## Task 1.1: `TimelineEntry.locked` Column

**Files:**
- Modify: `database/models.py:434-470` (Class `TimelineEntry`)
- Modify: `database/migrations.py` (neue Migration ans Ende)
- Test: `tests/test_database/test_timeline_entry_locked_column.py`

- [ ] **Step 1: Failing Test schreiben**

```python
# tests/test_database/test_timeline_entry_locked_column.py
import pytest
from sqlalchemy import inspect
from database import engine, init_db
from database.models import TimelineEntry, Project
from database.session import DBSession


def test_timeline_entry_has_locked_column():
    init_db()
    cols = {c["name"] for c in inspect(engine).get_columns("timeline_entries")}
    assert "locked" in cols


def test_timeline_entry_locked_defaults_false():
    init_db()
    with DBSession(engine) as s:
        p = Project(name="locked-default-test")
        s.add(p)
        s.flush()
        e = TimelineEntry(project_id=p.id, track="video", media_id=1, start_time=0.0)
        s.add(e)
        s.commit()
        s.refresh(e)
        assert e.locked is False
```

- [ ] **Step 2: Test ausführen, Fail bestätigen**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_database/test_timeline_entry_locked_column.py -v --tb=short
```

Erwartet: FAIL — `'locked' in cols` schlägt fehl.

- [ ] **Step 3: Column zu `TimelineEntry` hinzufügen**

```python
# database/models.py — innerhalb class TimelineEntry, nach contrast = Column(...)
locked = Column(Boolean, nullable=False, default=False, server_default="0")
```

`Boolean` ist bereits importiert; falls nicht, am File-Anfang:

```python
from sqlalchemy import Boolean
```

- [ ] **Step 4: Migration in `database/migrations.py` ergänzen**

Suche das letzte `def _migrate_<name>(conn):` und füge danach hinzu:

```python
def _migrate_timeline_entry_locked(conn):
    """SCHNITT-Redesign 2026-05-09: locked-Flag fuer Clip-Locking."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(timeline_entries)").fetchall()}
    if "locked" not in cols:
        conn.execute("ALTER TABLE timeline_entries ADD COLUMN locked BOOLEAN NOT NULL DEFAULT 0")
```

In der Migrations-Loop am Ende der Liste registrieren:

```python
MIGRATIONS = [
    ...,
    _migrate_timeline_entry_locked,
]
```

- [ ] **Step 5: Test ausführen, Pass bestätigen**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_database/test_timeline_entry_locked_column.py -v --tb=short
```

Erwartet: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add database/models.py database/migrations.py tests/test_database/test_timeline_entry_locked_column.py
git commit -m "feat(schnitt): add locked column to timeline_entries"
```

- [ ] **Step 7: Vault-Update**

Vault-Pfad: `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\schnitt-workspace-redesign-2026-05-09.md`. Status-Tabelle Eintrag „Phase 01 / Task 1.1 ✅ commit `<hash>`" hinzufügen.

---

## Task 1.2: `TimelineSnapshot`-Tabelle

**Files:**
- Modify: `database/models.py` (am Ende, nach existierenden Klassen)
- Modify: `database/migrations.py`
- Test: `tests/test_database/test_timeline_snapshot_table.py`

- [ ] **Step 1: Failing Test schreiben**

```python
# tests/test_database/test_timeline_snapshot_table.py
import pytest
from sqlalchemy import inspect
from database import engine, init_db
from database.models import TimelineSnapshot, Project
from database.session import DBSession


def test_timeline_snapshot_table_exists():
    init_db()
    tables = inspect(engine).get_table_names()
    assert "timeline_snapshots" in tables


def test_timeline_snapshot_create_and_load():
    init_db()
    with DBSession(engine) as s:
        p = Project(name="snap-test")
        s.add(p)
        s.flush()
        snap = TimelineSnapshot(
            project_id=p.id, version=1, label="initial", payload_json='{"clips":[]}'
        )
        s.add(snap)
        s.commit()
        loaded = s.query(TimelineSnapshot).filter_by(project_id=p.id).one()
        assert loaded.version == 1
        assert loaded.label == "initial"
        assert loaded.payload_json == '{"clips":[]}'
```

- [ ] **Step 2: Test ausführen, Fail bestätigen**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_database/test_timeline_snapshot_table.py -v --tb=short
```

Erwartet: FAIL — `ImportError: cannot import name 'TimelineSnapshot'`.

- [ ] **Step 3: Modell hinzufügen**

```python
# database/models.py — am Ende, nach TimelineEntry / AnalysisStatus
class TimelineSnapshot(Base):
    """Snapshot des Timeline-State für Versionierung (Hybrid-Undo)."""
    __tablename__ = "timeline_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    version = Column(Integer, nullable=False)
    label = Column(String, nullable=True)
    payload_json = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index("idx_snapshot_project_version", "project_id", "version"),
    )

    def __repr__(self):
        return f"<TimelineSnapshot(id={self.id}, project_id={self.project_id}, v={self.version})>"
```

`Index`, `DateTime`, `datetime`, `Text` müssen importiert sein. Falls nicht, am File-Anfang ergänzen.

- [ ] **Step 4: Migration ergänzen**

```python
def _migrate_timeline_snapshots(conn):
    """SCHNITT-Redesign 2026-05-09: Tabelle fuer persistente Timeline-Snapshots."""
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "timeline_snapshots" not in tables:
        conn.execute("""
            CREATE TABLE timeline_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                version INTEGER NOT NULL,
                label TEXT,
                payload_json TEXT NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "CREATE INDEX idx_snapshot_project_version "
            "ON timeline_snapshots(project_id, version)"
        )
```

In `MIGRATIONS`-Liste registrieren.

- [ ] **Step 5: Test ausführen, Pass bestätigen**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_database/test_timeline_snapshot_table.py -v --tb=short
```

Erwartet: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add database/models.py database/migrations.py tests/test_database/test_timeline_snapshot_table.py
git commit -m "feat(schnitt): add timeline_snapshots table"
```

- [ ] **Step 7: Vault-Update.**

---

## Task 1.3: `ProjectNote`-Tabelle

**Files:**
- Modify: `database/models.py`
- Modify: `database/migrations.py`
- Test: `tests/test_database/test_project_notes_table.py`

- [ ] **Step 1: Failing Test schreiben**

```python
# tests/test_database/test_project_notes_table.py
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError
from database import engine, init_db
from database.models import ProjectNote, Project
from database.session import DBSession


def test_project_notes_table_exists():
    init_db()
    tables = inspect(engine).get_table_names()
    assert "project_notes" in tables


def test_project_notes_unique_per_project():
    init_db()
    with DBSession(engine) as s:
        p = Project(name="notes-test")
        s.add(p)
        s.flush()
        s.add(ProjectNote(project_id=p.id, content_md="first"))
        s.commit()
        s.add(ProjectNote(project_id=p.id, content_md="second"))
        with pytest.raises(IntegrityError):
            s.commit()
```

- [ ] **Step 2: Test ausführen, Fail bestätigen**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_database/test_project_notes_table.py -v --tb=short
```

Erwartet: FAIL — `cannot import name 'ProjectNote'`.

- [ ] **Step 3: Modell hinzufügen**

```python
# database/models.py — am Ende
class ProjectNote(Base):
    """Markdown-Notes pro Projekt (Sub-Tab RL & Notes)."""
    __tablename__ = "project_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    content_md = Column(Text, nullable=False, default="")
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self):
        return f"<ProjectNote(project_id={self.project_id}, len={len(self.content_md)})>"
```

- [ ] **Step 4: Migration ergänzen**

```python
def _migrate_project_notes(conn):
    """SCHNITT-Redesign 2026-05-09: Tabelle fuer Markdown-Notes pro Projekt."""
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}
    if "project_notes" not in tables:
        conn.execute("""
            CREATE TABLE project_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL UNIQUE
                    REFERENCES projects(id) ON DELETE CASCADE,
                content_md TEXT NOT NULL DEFAULT '',
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """)
```

Registrieren in `MIGRATIONS`.

- [ ] **Step 5: Test ausführen, Pass bestätigen**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_database/test_project_notes_table.py -v --tb=short
```

Erwartet: 2 passed.

- [ ] **Step 6: Commit**

```bash
git add database/models.py database/migrations.py tests/test_database/test_project_notes_table.py
git commit -m "feat(schnitt): add project_notes table"
```

- [ ] **Step 7: Vault-Update.**

---

## Task 1.4: Migrations-Idempotenz-Test

**Files:**
- Test: `tests/test_database/test_schnitt_migrations_idempotent.py`

- [ ] **Step 1: Test schreiben**

```python
# tests/test_database/test_schnitt_migrations_idempotent.py
from database import init_db
from database.migrations import (
    _migrate_timeline_entry_locked,
    _migrate_timeline_snapshots,
    _migrate_project_notes,
)
from database import engine


def test_run_all_three_twice_does_not_raise():
    init_db()
    with engine.begin() as conn:
        for fn in (_migrate_timeline_entry_locked,
                   _migrate_timeline_snapshots,
                   _migrate_project_notes):
            fn(conn)
            fn(conn)  # zweiter Lauf darf nicht crashen
```

- [ ] **Step 2: Test ausführen, Pass erwartet**

```text
"C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_database/test_schnitt_migrations_idempotent.py -v --tb=short
```

Erwartet: 1 passed (Migrations sind idempotent durch Existenz-Checks in Step 3 jeder Task).

- [ ] **Step 3: Commit**

```bash
git add tests/test_database/test_schnitt_migrations_idempotent.py
git commit -m "test(schnitt): migrations idempotent on re-run"
```

- [ ] **Step 4: Vault-Update.**

---

## Phasen-Abschluss

Nach Task 1.4 ist Phase 01 fertig. Vault-Plan-Status auf „Phase 01 ✅ abgeschlossen, commit-Range `<first>..<last>`" setzen.

Nächste Phase: [02_DATA_SERVICES.md](02_DATA_SERVICES.md).
