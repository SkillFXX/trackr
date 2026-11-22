"""Recover the Trackr history deleted by the old 30-day retention.

SQLite does not wipe deleted rows: their pages are only marked as free and are
reused little by little. This script scans the whole database file for
raw_logs records that are no longer in the table and writes a NEW database
containing the current rows + the recovered ones. The source file is never
modified.

Usage (Trackr must be closed):
    python tools/recover_history.py "%APPDATA%\\Trackr\\trackr.db" trackr_recupere.db

Then keep a backup of the original trackr.db and replace it with the new file.
"""
import sqlite3
import struct
import sys
import os
from datetime import datetime

MAX_ROW_DURATION = 3700  # longer rows are sleep artefacts of old versions


def read_varint(buf, i):
    value = 0
    for k in range(9):
        byte = buf[i + k]
        if k == 8:
            return (value << 8) | byte, i + 9
        value = (value << 7) | (byte & 0x7F)
        if byte < 0x80:
            return value, i + k + 1
    return value, i + 9


def decode_record(buf, i, limit):
    """Decode a raw_logs record whose header starts at `i`, or return None."""
    header_size, j = read_varint(buf, i)
    if header_size < 6 or header_size > 20 or i + header_size > limit:
        return None
    types = []
    while j < i + header_size:
        t, j = read_varint(buf, j)
        types.append(t)
    if len(types) not in (6, 7):
        return None

    pos = i + header_size
    values = []
    for t in types:
        if t == 0:
            values.append(None)
        elif 1 <= t <= 6:
            size = (0, 1, 2, 3, 4, 6, 8)[t]
            values.append(int.from_bytes(buf[pos:pos + size], 'big', signed=True))
            pos += size
        elif t in (8, 9):
            values.append(t - 8)
        elif t >= 13 and t % 2 == 1:
            size = (t - 13) // 2
            values.append(buf[pos:pos + size].decode('utf-8', 'strict'))
            pos += size
        else:
            return None
        if pos > limit:
            return None

    _, ts, app, title, status, duration = values[:6]
    end_ts = values[6] if len(values) == 7 else None
    if not (isinstance(ts, int) and 1_600_000_000 < ts < 2_100_000_000
            and isinstance(app, str) and app
            and status in ('active', 'idle', 'fullscreen')
            and isinstance(duration, int) and 0 < duration < 200_000
            and (title is None or isinstance(title, str))
            and (end_ts is None or isinstance(end_ts, int))):
        return None

    if end_ts is None:
        # Old format: `timestamp` was the END of the tick
        start, end = ts - duration, ts
    else:
        start, end = ts, end_ts
    if duration > MAX_ROW_DURATION:
        start, duration = end - 5, 5
    return start, app, title, status, duration, end


def scan(path):
    data = open(path, 'rb').read()
    found = {}
    for i in range(100, len(data) - 10):
        if data[i] not in (7, 8, 9, 10, 11, 12):  # plausible record header sizes
            continue
        try:
            rec = decode_record(data, i, min(len(data), i + 8192))
        except (UnicodeDecodeError, IndexError):
            continue
        if rec:
            found[(rec[0], rec[1], rec[3])] = rec
    return found


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src, dst = sys.argv[1], sys.argv[2]
    if os.path.abspath(src) == os.path.abspath(dst):
        sys.exit("The output file must be different from the source file.")
    if os.path.exists(dst):
        sys.exit(f"{dst} already exists.")

    # 1. Copy the current database (consistent copy, WAL included)
    source = sqlite3.connect(f'file:{src}?mode=ro', uri=True)
    target = sqlite3.connect(dst)
    source.backup(target)
    source.close()

    columns = [r[1] for r in target.execute('PRAGMA table_info(raw_logs)')]
    if 'end_timestamp' not in columns:
        target.execute('ALTER TABLE raw_logs ADD COLUMN end_timestamp INTEGER')
        target.execute('UPDATE raw_logs SET end_timestamp = timestamp, timestamp = timestamp - duration '
                       'WHERE end_timestamp IS NULL')
    target.execute('UPDATE raw_logs SET duration = 5, timestamp = end_timestamp - 5 WHERE duration > ?',
                   (MAX_ROW_DURATION,))

    existing = {(r[0], r[1], r[2]) for r in target.execute('SELECT timestamp, app_name, status FROM raw_logs')}

    # 2. Scan the raw file for deleted records
    found = scan(src)
    missing = [r for key, r in found.items() if key not in existing]
    missing.sort()

    target.executemany('''
        INSERT INTO raw_logs (timestamp, app_name, window_title, status, duration, end_timestamp)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', missing)
    target.execute('PRAGMA user_version = 2')
    target.commit()

    first = target.execute('SELECT MIN(timestamp) FROM raw_logs').fetchone()[0]
    print(f"Current rows   : {len(existing)}")
    print(f"Recovered rows : {len(missing)}")
    if first:
        print(f"History now starts on {datetime.fromtimestamp(first):%d/%m/%Y}")
    for month, hours in target.execute('''
        SELECT strftime('%Y-%m', datetime(timestamp, 'unixepoch', 'localtime')) m,
               ROUND(SUM(CASE WHEN status != 'idle' THEN duration END) / 3600.0, 1)
        FROM raw_logs GROUP BY m ORDER BY m'''):
        print(f"  {month} : {hours} h actives")
    target.execute('VACUUM')
    target.close()
    print(f"Written to {dst}")


if __name__ == '__main__':
    main()
