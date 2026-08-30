"""Daily snapshot of the capture database — TEMPLATE-adjacent ops script, runs on the VPS.

Uses sqlite3's online backup API (safe against a concurrently open database, unlike cp),
gzips to backups/capture-YYYYMMDD.db.gz, and prunes snapshots older than KEEP_DAYS.
The token DB is deliberately not backed up: its contents expire at 06:00 IST daily.

Run by deploy/options-backup.timer at 10:20 IST Mon-Fri, after the capture window closes.
"""

import gzip
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

SRC = Path("data/options/capture.db")
BACKUP_DIR = Path("backups")
# Full snapshots each contain all history, so old generations are redundant; a handful
# guards against a corrupt latest copy. 60 generations of a linearly growing DB would
# consume the disk quadratically — offsite copies are the disaster layer, not this.
KEEP_COUNT = 7
DISK_WARN_FRACTION = 0.15  # warn to Telegram when free space drops below 15%


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

    snapshots = sorted(BACKUP_DIR.glob("capture-*.db.gz"))
    pruned = 0
    for old in snapshots[:-KEEP_COUNT]:
        old.unlink()
        pruned += 1

    usage = shutil.disk_usage("/")
    free_frac = usage.free / usage.total
    print(
        f"backup ok: {dst} ({dst.stat().st_size} bytes), pruned {pruned}, "
        f"disk free {free_frac:.0%}"
    )
    if free_frac < DISK_WARN_FRACTION:
        try:
            from app.options.notify import send

            send(
                f"⚠️ VPS disk low: {free_frac:.0%} free "
                f"({usage.free // 2**30} GiB of {usage.total // 2**30} GiB). "
                "Capture keeps running, but act soon."
            )
        except Exception:
            pass  # the warning is best-effort; the backup itself succeeded
    return 0


if __name__ == "__main__":
    sys.exit(main())
