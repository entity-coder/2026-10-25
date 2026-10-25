"""Backup and restore for FeeTrack.

A backup is a plain copy of the SQLite file, timestamped, in the
``backups/`` folder next to the database. A restore first saves the
current database as a ``.safety`` copy, so a bad restore can always be
undone by renaming that file back — the same safety-copy pattern as
the earlier sellable apps.
"""

import shutil
from datetime import datetime
from pathlib import Path


def backup_db(db_path, backup_dir=None):
    """Copy the database to a timestamped file; return its path."""
    db_path = Path(db_path)
    backup_dir = Path(backup_dir) if backup_dir else db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = backup_dir / f"feetrack-backup-{stamp}.db"
    shutil.copyfile(db_path, dest)
    return dest


def restore_db(db_path, backup_file):
    """Replace the database with ``backup_file``, keeping a safety copy."""
    db_path = Path(db_path)
    safety = db_path.with_suffix(".safety.db")
    if db_path.exists():
        shutil.copyfile(db_path, safety)
    shutil.copyfile(backup_file, db_path)
    return safety
