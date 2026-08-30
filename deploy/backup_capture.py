"""Daily snapshot of the capture database — TEMPLATE-adjacent ops script, runs on the VPS.

Two outputs per run:
1. Full local snapshot via sqlite3's online backup API (safe against a concurrently open
   database, unlike cp), gzipped to backups/capture-YYYYMMDD.db.gz, last KEEP_COUNT kept.
2. Today's rows only, exported to a small standalone SQLite file, gzipped and sent to the
   Telegram chat via notify.send_document — an append-only OFFSITE archive. Per-day files
   stay ~2-3 MB forever; a full snapshot would outgrow Telegram's 50 MB bot cap in weeks.

The token DB is deliberately not backed up: its contents expire at 06:00 IST daily.
Run by deploy/options-backup.timer at 10:20 IST Mon-Fri, after the capture window closes.
"""

import gzip
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

# Run as a plain script (python deploy/backup_capture.py), so the repo root — this file's
# parent's parent — must be put on sys.path before app.* becomes importable.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.options.notify import send_document  # noqa: E402

SRC = Path("data/options/capture.db")
BACKUP_DIR = Path("backups")
# Full snapshots each contain all history, so old generations are redundant; a handful
# guards against a corrupt latest copy. 60 generations of a linearly growing DB would
# consume the disk quadratically — offsite copies are the disaster layer, not this.
KEEP_COUNT = 7
DISK_WARN_FRACTION = 0.15  # warn to Telegram when free space drops below 15%


DAY_TABLES = ("chain_snapshots", "index_snapshots", "heartbeats")


def _gzip_file(src: Path, dst: Path) -> None:
    with open(src, "rb") as f_in, gzip.open(dst, "wb") as f_out:
        while chunk := f_in.read(1 << 20):
            f_out.write(chunk)


def export_and_send_day(today: date) -> None:
    """Export today's rows to a standalone SQLite file and ship it to Telegram.

    Skipped (silently, one stdout line) when today produced no market rows — weekends,
    holidays — so the chat only receives real data. Local per-day files rotate with the
    same KEEP_COUNT; Telegram holds the permanent archive.
    """
    iso_day = today.isoformat()  # ts columns are IST ISO-8601 text: prefix-match the date
    day_raw = BACKUP_DIR / f"day-{today:%Y%m%d}.db"
    day_gz = BACKUP_DIR / f"day-{today:%Y%m%d}.db.gz"

    day_raw.unlink(missing_ok=True)
    conn = sqlite3.connect(day_raw)
    try:
        conn.execute("ATTACH DATABASE ? AS full", (str(SRC),))
        market_rows = 0
        for table in DAY_TABLES:
            conn.execute(
                f"CREATE TABLE {table} AS SELECT * FROM full.{table} WHERE ts LIKE ? || '%'",  # noqa: S608 — table names from a module constant
                (iso_day,),
            )
            if table != "heartbeats":
                market_rows += conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
        conn.commit()
    finally:
        conn.close()

    if market_rows == 0:
        day_raw.unlink(missing_ok=True)
        print(f"no market rows for {iso_day}; day export skipped")
        return

    _gzip_file(day_raw, day_gz)
    day_raw.unlink()
    sent = send_document(day_gz, caption=f"📦 Capture {iso_day}: {market_rows} rows")
    status = "sent" if sent else "NOT sent"
    print(f"day export: {day_gz} ({day_gz.stat().st_size} bytes, {market_rows} rows), telegram={status}")

    for old in sorted(BACKUP_DIR.glob("day-*.db.gz"))[:-KEEP_COUNT]:
        old.unlink()


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

    _gzip_file(tmp, dst)
    tmp.unlink()

    export_and_send_day(date.today())

    snapshots = sorted(BACKUP_DIR.glob("capture-*.db.gz"))
    pruned = 0
    for old in snapshots[:-KEEP_COUNT]:
        old.unlink()
        pruned += 1

    usage = shutil.disk_usage("/")
    free_frac = usage.free / usage.total
    print(f"backup ok: {dst} ({dst.stat().st_size} bytes), pruned {pruned}, " f"disk free {free_frac:.0%}")
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
