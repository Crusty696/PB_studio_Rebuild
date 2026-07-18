import pytest
from unittest.mock import patch, MagicMock
from database.migrations import _verify_required_tables

def test_database_initialization_guard_missing_table():
    """B7: Verifiziert, dass _verify_required_tables einen RuntimeError wirft,
    wenn Pflicht-Tabellen in der Datenbank fehlen."""
    
    # Mocking inspect(engine).get_table_names() to simulate missing tables
    mock_inspector = MagicMock()
    mock_inspector.get_table_names.return_value = ["projects", "audio_tracks"] # analysis_status und andere fehlen
    
    with patch("sqlalchemy.inspect", return_value=mock_inspector):
        with pytest.raises(RuntimeError) as exc_info:
            _verify_required_tables()
            
        assert "Datenbank-Initialisierung unvollstaendig!" in str(exc_info.value)
        assert "analysis_status" in str(exc_info.value)

def test_database_initialization_guard_all_tables_present():
    """B7: Verifiziert, dass _verify_required_tables erfolgreich durchlaeuft,
    wenn alle definierten Tabellen vorhanden sind."""
    from database import Base
    
    mock_inspector = MagicMock()
    # Simuliert, dass alle Tabellen vorhanden sind
    mock_inspector.get_table_names.return_value = list(Base.metadata.tables.keys())
    
    with patch("sqlalchemy.inspect", return_value=mock_inspector):
        # Sollte ohne Exception durchlaufen
        _verify_required_tables()


def test_fresh_db_alembic_failure_fails_fast():
    """B7-Rest: Alembic-Fehler auf Fresh-DB darf nicht mehr geschluckt werden.

    Vorher: except-Block loggte nur ein Warning und die App lief mit
    unvollstaendigem Schema weiter (mem_*/struct_*-Tabellen entstehen nur
    durch Alembic). Jetzt: Fail-fast analog B-626."""
    from database import migrations

    mock_inspector = MagicMock()
    mock_inspector.get_table_names.return_value = []  # Fresh-DB

    with patch("sqlalchemy.inspect", return_value=mock_inspector), \
         patch.object(migrations, "get_raw_engine"), \
         patch.object(migrations, "engine"), \
         patch.object(migrations.Base.metadata, "create_all"), \
         patch("alembic.command.stamp"), \
         patch.object(migrations, "_run_alembic_migrations",
                      side_effect=RuntimeError("alembic kaputt")), \
         patch.object(migrations, "_seed_defaults") as mock_seed:
        with pytest.raises(RuntimeError, match="alembic kaputt"):
            migrations.init_db()
        mock_seed.assert_not_called()
