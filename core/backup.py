import sqlite3
import shutil
import time
from pathlib import Path
from core.db import DB_PATH


def create_db_backup(backup_dir: str = None) -> tuple[bool, str]:
    """
    Safely create an online, consistent backup of the SQLite database using SQLite's Backup API.
    Does not lock writers or corrupt concurrent transactions.
    """
    src_path = Path(DB_PATH)
    if not src_path.exists():
        return False, f"Source database not found at {src_path}"

    dest_dir = Path(backup_dir) if backup_dir else src_path.parent / "backups"
    dest_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    dest_path = dest_dir / f"bloom_backup_{timestamp}.db"

    try:
        # Use sqlite3 online backup API
        src_conn = sqlite3.connect(str(src_path))
        dest_conn = sqlite3.connect(str(dest_path))
        with dest_conn:
            src_conn.backup(dest_conn)
        dest_conn.close()
        src_conn.close()

        # Run integrity check on backup
        verify_conn = sqlite3.connect(str(dest_path))
        res = verify_conn.execute("PRAGMA integrity_check").fetchone()
        verify_conn.close()

        if res and res[0] == "ok":
            return True, str(dest_path)
        return False, f"Integrity check failed: {res}"
    except Exception as exc:
        return False, f"Backup error: {type(exc).__name__} {exc}"


def verify_db_integrity() -> tuple[bool, str]:
    """Verify integrity of active database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        res = conn.execute("PRAGMA integrity_check").fetchone()
        conn.close()
        return (True, "Database integrity verified (ok)") if (res and res[0] == "ok") else (False, str(res))
    except Exception as exc:
        return False, str(exc)
