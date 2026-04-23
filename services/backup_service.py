import os
import shutil
import logging
import datetime
from pathlib import Path
from database.session import APP_ROOT

logger = logging.getLogger(__name__)

class BackupService:
    """
    Service for resilient SQLite backups of the pb_studio.db.
    Implements Phase P9 (T9.1) of the Studio Brain Plan.
    """
    
    BACKUP_DIR = APP_ROOT / "storage" / "backups"
    DB_PATH = APP_ROOT / "pb_studio.db"
    RETENTION_DAYS = 14

    @classmethod
    def create_backup(cls, label: str = "auto") -> Path | None:
        """
        Creates a backup of the current database file.
        
        Args:
            label: A label to include in the backup filename.
            
        Returns:
            The path to the created backup file, or None if failed.
        """
        try:
            if not cls.BACKUP_DIR.exists():
                cls.BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                logger.info(f"Created backup directory: {cls.BACKUP_DIR}")

            if not cls.DB_PATH.exists():
                logger.error(f"Database file not found at {cls.DB_PATH}")
                return None

            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"pb_studio_{label}_{timestamp}.db"
            backup_path = cls.BACKUP_DIR / backup_filename

            # Using shutil.copy2 for "Fast file copy" as requested.
            # Note: In WAL mode, this might miss uncommitted changes in the -wal file.
            # For a production-grade live backup, sqlite3's backup API would be safer,
            # but shutil is faster for large files if the risk is acceptable.
            shutil.copy2(cls.DB_PATH, backup_path)
            
            # Also copy WAL and SHM files if they exist to ensure consistency
            wal_path = cls.DB_PATH.with_suffix(".db-wal")
            if wal_path.exists():
                shutil.copy2(wal_path, backup_path.with_suffix(".db-wal"))
            
            shm_path = cls.DB_PATH.with_suffix(".db-shm")
            if shm_path.exists():
                shutil.copy2(shm_path, backup_path.with_suffix(".db-shm"))

            logger.info(f"Backup created: {backup_path}")
            
            # Run cleanup of old backups
            cls.cleanup_old_backups()
            
            return backup_path
            
        except Exception as e:
            logger.error(f"Failed to create backup: {e}", exc_info=True)
            return None

    @classmethod
    def cleanup_old_backups(cls):
        """
        Deletes backups older than RETENTION_DAYS.
        """
        try:
            if not cls.BACKUP_DIR.exists():
                return

            now = datetime.datetime.now()
            retention_delta = datetime.timedelta(days=cls.RETENTION_DAYS)
            
            count = 0
            for file in cls.BACKUP_DIR.glob("pb_studio_*.db*"):
                file_mtime = datetime.datetime.fromtimestamp(file.stat().st_mtime)
                if now - file_mtime > retention_delta:
                    try:
                        file.unlink()
                        count += 1
                    except Exception as e:
                        logger.warning(f"Failed to delete old backup {file}: {e}")
            
            if count > 0:
                logger.info(f"Cleaned up {count} old backup files.")
                
        except Exception as e:
            logger.error(f"Error during backup cleanup: {e}", exc_info=True)

    @classmethod
    def get_backup_stats(cls):
        """Returns statistics about existing backups."""
        if not cls.BACKUP_DIR.exists():
            return {"count": 0, "total_size_mb": 0}
            
        backups = list(cls.BACKUP_DIR.glob("pb_studio_*.db"))
        total_size = sum(f.stat().st_size for f in backups)
        
        return {
            "count": len(backups),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "directory": str(cls.BACKUP_DIR)
        }
