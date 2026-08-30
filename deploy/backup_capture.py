"""Daily snapshot of the capture database — TEMPLATE-adjacent ops script, runs on the VPS.

Uses sqlite3's online backup API (safe against a concurrently open database, unlike cp),
gzips to backups/capture-YYYYMMDD.db.gz, and prunes snapshots older than KEEP_DAYS.
The token DB is deliberately not backed up: its contents expire at 06:00 IST daily.

Run by deploy/options-backup.timer at 10:20 IST Mon-Fri, after the capture window closes.
"""

import gzip
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

SRC = Path("data/options/capture.db")
BACKUP_DIR = Path("backups")
KEEP_DAYS = 60


def main() -> int:
    if not SRC.exists():
        print(f"nothing to back up: {SRC} missing")
        return 0
    BACKUP_DIR.mkdir(exist_ok=True)
    dst = BACKUP_DIR / f"capture-{date.today():%Y%m%d}.db.gz"
    tmp = BACKUP_DIR / "capture-backup.tmp.db"

    src_conn = sqlite3.connect(SRC)
    try:
        dst_conn = sqlite3.connect(tmp)
        try:
            src_conn.backup(dst_conn)
        finally:
            dst_conn.close()
    finally:
        src_conn.close()

    with open(tmp, "rb") as f_in, gzip.open(dst, "wb") as f_out:
        while chunk := f_in.read(1 << 20):
            f_out.write(chunk)
    tmp.unlink()

    cutoff = time.time() - KEEP_DAYS * 86400
    pruned = 0
    for old in BACKUP_DIR.glob("capture-*.db.gz"):
        if old.stat().st_mtime < cutoff:
            old.unlink()
            pruned += 1

    print(f"backup ok: {dst} ({dst.stat().st_size} bytes), pruned {pruned}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
