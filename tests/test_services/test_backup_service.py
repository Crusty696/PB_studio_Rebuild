import os
import pytest
import datetime
import shutil
from pathlib import Path
from services.backup_service import BackupService
from database.session import APP_ROOT

@pytest.fixture
def temp_backup_dir(tmp_path):
    """Fixture to provide a temporary backup directory."""
    original_dir = BackupService.BACKUP_DIR
    BackupService.BACKUP_DIR = tmp_path / "backups"
    BackupService.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    yield BackupService.BACKUP_DIR
    # Reset to original
    BackupService.BACKUP_DIR = original_dir

@pytest.fixture
def dummy_db(tmp_path):
    """Fixture to provide a dummy database file."""
    original_db = BackupService.DB_PATH
    db_path = tmp_path / "pb_studio.db"
    db_path.write_text("dummy database content")
    BackupService.DB_PATH = db_path
    yield db_path
    # Reset to original
    BackupService.DB_PATH = original_db

def test_create_backup(temp_backup_dir, dummy_db):
    """Tests if a backup file is created."""
    backup_path = BackupService.create_backup(label="test")
    
    assert backup_path is not None
    assert backup_path.exists()
    assert backup_path.name.startswith("pb_studio_test_")
    assert backup_path.read_text() == "dummy database content"

def test_cleanup_old_backups(temp_backup_dir):
    """Tests if old backups are correctly deleted."""
    # Create some "old" backups (15 days ago)
    old_time = datetime.datetime.now() - datetime.timedelta(days=15)
    old_timestamp = old_time.timestamp()
    
    for i in range(3):
        old_file = temp_backup_dir / f"pb_studio_old_{i}.db"
        old_file.write_text("old content")
        os.utime(old_file, (old_timestamp, old_timestamp))
        
    # Create some "new" backups (1 day ago)
    new_time = datetime.datetime.now() - datetime.timedelta(days=1)
    new_timestamp = new_time.timestamp()
    
    for i in range(2):
        new_file = temp_backup_dir / f"pb_studio_new_{i}.db"
        new_file.write_text("new content")
        os.utime(new_file, (new_timestamp, new_timestamp))
        
    assert len(list(temp_backup_dir.glob("pb_studio_*.db"))) == 5
    
    # Run cleanup
    BackupService.cleanup_old_backups()
    
    # Check results
    remaining_files = list(temp_backup_dir.glob("pb_studio_*.db"))
    assert len(remaining_files) == 2
    for file in remaining_files:
        assert "new" in file.name
        assert "old" not in file.name

def test_rolling_backup_limit(temp_backup_dir, dummy_db):
    """Tests if create_backup triggers cleanup."""
    # Create 20 old backups
    old_time = datetime.datetime.now() - datetime.timedelta(days=20)
    old_timestamp = old_time.timestamp()
    
    for i in range(20):
        old_file = temp_backup_dir / f"pb_studio_veryold_{i}.db"
        old_file.write_text("garbage")
        os.utime(old_file, (old_timestamp, old_timestamp))
        
    assert len(list(temp_backup_dir.glob("pb_studio_*.db"))) == 20
    
    # Creating a new backup should trigger cleanup
    BackupService.create_backup(label="fresh")
    
    # All 20 old ones should be gone, only the fresh one should remain
    remaining_files = list(temp_backup_dir.glob("pb_studio_*.db"))
    assert len(remaining_files) == 1
    assert "fresh" in remaining_files[0].name
