import sqlite3
import os
import time
import threading
from datetime import datetime, timedelta
from .config import APP_DATA_DIR, config

DB_FILE = os.path.join(APP_DATA_DIR, 'trackr.db')

ACTIVE_SQL = "status IN ('active', 'fullscreen')"

# Consecutive records of the same app separated by less than this many seconds
# belong to the same session.
SESSION_GAP_MIN = 30

# Session length buckets (label, upper bound in seconds)
SESSION_BUCKETS = [
    ("< 1 min", 60),
    ("1-5 min", 300),
    ("5-15 min", 900),
    ("15-30 min", 1800),
    ("30-60 min", 3600),
    ("> 1h", None),
]

DAY_NAMES = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]


def _local_hour_key(ts):
    return time.strftime('%Y%m%d%H', time.localtime(ts))


def _minutes_to_hhmm(minutes):
    if minutes is None:
        return "-"
    minutes = int(round(minutes)) % (24 * 60)
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


class DatabaseManager:
    def __init__(self, path=DB_FILE):
        # One connection shared between the tracker thread and the pywebview API
        # threads: every access goes through this lock.
        self.lock = threading.RLock()
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        try:
            self.conn.execute('PRAGMA journal_mode=WAL')
        except sqlite3.DatabaseError:
            pass
        self._last_segment = None
        self._create_tables()

    # ------------------------------------------------------------------ schema

    def _create_tables(self):
        with self.lock:
            cursor = self.conn.cursor()
            # `timestamp` = start of the segment, `end_timestamp` = end of the segment.
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS raw_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp INTEGER NOT NULL,
                    app_name TEXT NOT NULL,
                    window_title TEXT,
                    status TEXT NOT NULL, -- 'active', 'idle', 'fullscreen'
                    duration INTEGER NOT NULL,
                    end_timestamp INTEGER
                )
            ''')

            columns = [r['name'] for r in cursor.execute('PRAGMA table_info(raw_logs)').fetchall()]
            if 'end_timestamp' not in columns:
                cursor.execute('ALTER TABLE raw_logs ADD COLUMN end_timestamp INTEGER')
            # Legacy rows stored the END of a tick in `timestamp`: convert them to start/end.
            cursor.execute('''
                UPDATE raw_logs
                SET end_timestamp = timestamp, timestamp = timestamp - duration
                WHERE end_timestamp IS NULL
            ''')

            cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON raw_logs(timestamp)')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_app_name ON raw_logs(app_name)')
            self.conn.commit()

    # ------------------------------------------------------------------ writes

    def insert_log(self, app_name, window_title, status, duration, end_ts=None):
        """Record `duration` seconds ending at `end_ts`.

        Consecutive ticks with the same app / title / status are merged into a
        single row (as long as they stay within the same clock hour), which keeps
        the database small and gives exact session boundaries.
        """
        duration = int(duration)
        if duration <= 0:
            return
        end = int(end_ts if end_ts is not None else time.time())
        start = end - duration
        hour_key = _local_hour_key(start)

        with self.lock:
            cursor = self.conn.cursor()
            last = self._last_segment
            tolerance = max(10, duration)
            if (last and last['app_name'] == app_name and last['window_title'] == window_title
                    and last['status'] == status and last['hour_key'] == hour_key
                    and abs(start - last['end']) <= tolerance):
                cursor.execute(
                    'UPDATE raw_logs SET duration = duration + ?, end_timestamp = ? WHERE id = ?',
                    (duration, end, last['id'])
                )
                last['end'] = end
            else:
                cursor.execute('''
                    INSERT INTO raw_logs (timestamp, app_name, window_title, status, duration, end_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (start, app_name, window_title, status, duration, end))
                self._last_segment = {
                    'id': cursor.lastrowid, 'app_name': app_name, 'window_title': window_title,
                    'status': status, 'hour_key': hour_key, 'end': end,
                }
            self.conn.commit()

    def purge_old_data(self, days):
        """Delete records older than `days`."""
        try:
            days = int(days)
        except (TypeError, ValueError):
            return
        if days <= 0:
            return
        threshold_ts = int(time.time()) - (days * 86400)
        with self.lock:
            self.conn.execute('DELETE FROM raw_logs WHERE timestamp < ?', (threshold_ts,))
            self.conn.commit()

    def export_rows(self):
        with self.lock:
            return [dict(r) for r in self.conn.execute(
                'SELECT * FROM raw_logs ORDER BY timestamp ASC').fetchall()]

    # ------------------------------------------------------------------ helpers

    def _query(self, sql, params=()):
        with self.lock:
            return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    def _scalar(self, sql, params=()):
        with self.lock:
            row = self.conn.execute(sql, params).fetchone()
        if not row:
            return 0
        value = row[0]
        return value or 0

    def _format_duration(self, seconds):
        if not seconds or seconds <= 0:
            return "0m"
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        if h > 0:
            return f"{h}h {m:02d}m" if m > 0 else f"{h}h"
        if m == 0:
            return f"{int(seconds)}s"
        return f"{m}m"

    def _pct(self, part, total):
        return round((part / total) * 100, 1) if total else 0

    def _pct_change(self, current, previous):
        if previous:
            return round(((current - previous) / previous) * 100, 1)
        return None

    def _session_gap(self):
        try:
            interval = int(config.get("refresh_interval", 5))
        except (TypeError, ValueError):
            interval = 5
        return max(SESSION_GAP_MIN, interval * 3)

    def _calculate_streak(self, active_dates):
        if not active_dates:
            return 0
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        date_set = set(active_dates)

        current = today if str(today) in date_set else (yesterday if str(yesterday) in date_set else None)
        if not current:
            return 0

        streak = 0
        while str(current) in date_set:
            streak += 1
            current = current - timedelta(days=1)
        return streak

    def _segments(self, start_ts, end_ts, app_name=None):
        sql = '''
            SELECT app_name, window_title, status, timestamp AS start,
                   COALESCE(end_timestamp, timestamp + duration) AS end, duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ?
        '''
        params = [start_ts, end_ts]
        if app_name is not None:
            sql += ' AND app_name = ?'
            params.append(app_name)
        sql += ' ORDER BY timestamp ASC, id ASC'
        return self._query(sql, params)

    def _build_sessions(self, segments):
        """Group active segments into per-app sessions and idle segments into breaks."""
        gap = self._session_gap()
        sessions = []
        breaks = []
        switches = 0
        current = None
        current_break = None
        last_active_app = None

        for seg in segments:
            if seg['status'] == 'idle':
                if current:
                    sessions.append(current)
                    current = None
                if current_break and seg['start'] - current_break['end'] <= gap:
                    current_break['end'] = seg['end']
                    current_break['duration'] += seg['duration']
                else:
                    if current_break:
                        breaks.append(current_break)
                    current_break = {'start': seg['start'], 'end': seg['end'], 'duration': seg['duration']}
                continue

            if current_break:
                breaks.append(current_break)
                current_break = None

            if last_active_app is not None and seg['app_name'] != last_active_app:
                switches += 1
            last_active_app = seg['app_name']

            if current and current['app_name'] == seg['app_name'] and seg['start'] - current['end'] <= gap:
                current['end'] = max(current['end'], seg['end'])
                current['duration'] += seg['duration']
                titles = current['titles']
                titles[seg['window_title'] or ''] = titles.get(seg['window_title'] or '', 0) + seg['duration']
            else:
                if current:
                    sessions.append(current)
                current = {
                    'app_name': seg['app_name'],
                    'start': seg['start'],
                    'end': seg['end'],
                    'duration': seg['duration'],
                    'titles': {seg['window_title'] or '': seg['duration']},
                }

        if current:
            sessions.append(current)
        if current_break:
            breaks.append(current_break)

        for s in sessions:
            s['main_title'] = max(s['titles'], key=s['titles'].get) if s['titles'] else ''
            del s['titles']
        return sessions, breaks, switches

    def _session_to_dict(self, s):
        return {
            "app_name": s['app_name'],
            "category": config.get_category_for_app(s['app_name']),
            "title": s.get('main_title', ''),
            "start": s['start'],
            "end": s['end'],
            "start_label": datetime.fromtimestamp(s['start']).strftime('%H:%M'),
            "end_label": datetime.fromtimestamp(s['end']).strftime('%H:%M'),
            "date": datetime.fromtimestamp(s['start']).strftime('%Y-%m-%d'),
            "duration": s['duration'],
            "formatted": self._format_duration(s['duration']),
        }

    def _focus_stats(self, segments):
        """Session, switch, break and focus statistics for a list of segments."""
        sessions, breaks, switches = self._build_sessions(segments)
        total_active = sum(s['duration'] for s in sessions)
        active_hours = total_active / 3600.0

        # Sessions shorter than 10 seconds are mostly alt-tab noise.
        meaningful = [s for s in sessions if s['duration'] >= 10]
        sessions_count = len(meaningful)
        avg_session = int(sum(s['duration'] for s in meaningful) / sessions_count) if sessions_count else 0
        longest = max(sessions, key=lambda s: s['duration']) if sessions else None

        buckets = []
        for label, upper in SESSION_BUCKETS:
            buckets.append({"label": label, "count": 0, "duration": 0})
        for s in sessions:
            for i, (_, upper) in enumerate(SESSION_BUCKETS):
                if upper is None or s['duration'] < upper:
                    buckets[i]['count'] += 1
                    buckets[i]['duration'] += s['duration']
                    break
        for b in buckets:
            b['percentage'] = self._pct(b['duration'], total_active)
            b['formatted'] = self._format_duration(b['duration'])

        # Time spent in sessions of 25 minutes or more = deep work
        deep_work = sum(s['duration'] for s in sessions if s['duration'] >= 1500)

        switches_per_hour = round(switches / active_hours, 1) if active_hours >= 0.25 else 0
        if total_active == 0:
            focus_label, focus_status = "Aucune donnée", "none"
        elif switches_per_hour < 15:
            focus_label, focus_status = "Forte concentration", "excellent"
        elif switches_per_hour < 35:
            focus_label, focus_status = "Concentration modérée", "good"
        else:
            focus_label, focus_status = "Multitâche élevé", "dispersed"

        real_breaks = [b for b in breaks if b['duration'] >= 60]
        avg_break = int(sum(b['duration'] for b in real_breaks) / len(real_breaks)) if real_breaks else 0

        top_sessions = sorted(sessions, key=lambda s: s['duration'], reverse=True)[:5]

        return {
            "sessions_count": sessions_count,
            "avg_session": avg_session,
            "avg_session_formatted": self._format_duration(avg_session),
            "longest_session": self._session_to_dict(longest) if longest else None,
            "top_sessions": [self._session_to_dict(s) for s in top_sessions],
            "session_buckets": buckets,
            "switches": switches,
            "switches_per_hour": switches_per_hour,
            "focus_label": focus_label,
            "focus_status": focus_status,
            "deep_work": deep_work,
            "deep_work_formatted": self._format_duration(deep_work),
            "deep_work_pct": self._pct(deep_work, total_active),
            "breaks_count": len(real_breaks),
            "avg_break": avg_break,
            "avg_break_formatted": self._format_duration(avg_break),
        }, sessions

    def _app_totals(self, start_ts, end_ts):
        return self._query(f'''
            SELECT app_name, SUM(duration) AS total_duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND {ACTIVE_SQL}
            GROUP BY app_name
            ORDER BY total_duration DESC
        ''', (start_ts, end_ts))

    def _status_totals(self, start_ts, end_ts):
        rows = self._query('''
            SELECT status, SUM(duration) AS total
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ?
            GROUP BY status
        ''', (start_ts, end_ts))
        totals = {r['status']: r['total'] or 0 for r in rows}
        return {
            "active": totals.get('active', 0) + totals.get('fullscreen', 0),
            "fullscreen": totals.get('fullscreen', 0),
            "idle": totals.get('idle', 0),
        }

    def _daily_rhythm(self, start_ts, end_ts):
        """Average first / last activity time per day."""
        rows = self._query(f'''
            SELECT strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) AS day,
                   MIN(timestamp) AS first_ts,
                   MAX(COALESCE(end_timestamp, timestamp + duration)) AS last_ts,
                   SUM(duration) AS active
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND {ACTIVE_SQL}
            GROUP BY day
            HAVING active >= 300
        ''', (start_ts, end_ts))
        if not rows:
            return {
                "avg_start": "-", "avg_end": "-", "avg_span": 0, "avg_span_formatted": "-",
                "earliest_start": "-", "latest_end": "-", "days": 0,
            }

        def minutes_of_day(ts):
            d = datetime.fromtimestamp(ts)
            return d.hour * 60 + d.minute

        starts = [minutes_of_day(r['first_ts']) for r in rows]
        ends = []
        spans = []
        for r in rows:
            end_dt = datetime.fromtimestamp(r['last_ts'])
            day_dt = datetime.strptime(r['day'], '%Y-%m-%d')
            # Activity ending after midnight keeps counting for the day it started
            end_minutes = (end_dt - day_dt).total_seconds() / 60
            ends.append(end_minutes)
            spans.append(r['last_ts'] - r['first_ts'])

        avg_span = int(sum(spans) / len(spans))
        return {
            "avg_start": _minutes_to_hhmm(sum(starts) / len(starts)),
            "avg_end": _minutes_to_hhmm(sum(ends) / len(ends)),
            "earliest_start": _minutes_to_hhmm(min(starts)),
            "latest_end": _minutes_to_hhmm(max(ends)),
            "avg_span": avg_span,
            "avg_span_formatted": self._format_duration(avg_span),
            "days": len(rows),
        }

    # ------------------------------------------------------------------ dashboard

    def get_dashboard_stats(self, start_ts, end_ts, prev_start_ts=None, prev_end_ts=None):
        """Returns statistics for a given time range."""
        totals = self._status_totals(start_ts, end_ts)
        total_active = totals['active']

        prev_active = None
        if prev_start_ts is not None and prev_end_ts is not None:
            prev_active = self._status_totals(prev_start_ts, prev_end_ts)['active']

        apps = self._app_totals(start_ts, end_ts)
        top_apps = apps[:5]
        for app in top_apps:
            app['category'] = config.get_category_for_app(app['app_name'])
            app['percentage'] = self._pct(app['total_duration'], total_active)

        timeline = self._query(f'''
            SELECT strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) AS hour,
                   SUM(duration) AS duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND {ACTIVE_SQL}
            GROUP BY hour
            ORDER BY hour ASC
        ''', (start_ts, end_ts))

        peak_hour = None
        max_hour_dur = 0
        for item in timeline:
            if item['duration'] > max_hour_dur:
                max_hour_dur = item['duration']
                peak_hour = int(item['hour'])

        cat_map = {}
        for row in apps:
            cat = config.get_category_for_app(row['app_name'])
            cat_map[cat] = cat_map.get(cat, 0) + row['total_duration']
        top_categories = sorted(
            [{"category": k, "duration": v, "percentage": self._pct(v, total_active)} for k, v in cat_map.items()],
            key=lambda x: x["duration"], reverse=True
        )[:5]

        focus, _ = self._focus_stats(self._segments(start_ts, end_ts))
        rhythm = self._daily_rhythm(start_ts, end_ts)

        days_count = self._scalar(f'''
            SELECT COUNT(DISTINCT strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')))
            FROM raw_logs WHERE timestamp >= ? AND timestamp <= ? AND {ACTIVE_SQL}
        ''', (start_ts, end_ts))
        daily_average = int(total_active / days_count) if days_count else 0

        return {
            "total_active": total_active,
            "total_idle": totals['idle'],
            "total_fullscreen": totals['fullscreen'],
            "prev_total_active": prev_active,
            "active_pct_change": self._pct_change(total_active, prev_active),
            "apps_count": len(apps),
            "days_count": days_count,
            "daily_average": daily_average,
            "top_apps": top_apps,
            "timeline": timeline,
            "peak_hour": peak_hour,
            "top_categories": top_categories,
            "focus": focus,
            "rhythm": rhythm,
        }

    # ------------------------------------------------------------------ applications

    def get_all_apps_stats(self, start_ts, end_ts, search="", category_filter=""):
        segments = self._segments(start_ts, end_ts)
        sessions, _, _ = self._build_sessions(segments)

        per_app = {}
        for s in sessions:
            entry = per_app.setdefault(s['app_name'], {
                "app_name": s['app_name'], "total_duration": 0, "sessions_count": 0,
                "longest_session": 0, "last_used": 0,
            })
            entry['total_duration'] += s['duration']
            if s['duration'] >= 10:
                entry['sessions_count'] += 1
            entry['longest_session'] = max(entry['longest_session'], s['duration'])
            entry['last_used'] = max(entry['last_used'], s['end'])

        raw_apps = sorted(per_app.values(), key=lambda a: a['total_duration'], reverse=True)
        total_time = sum(a['total_duration'] for a in raw_apps)

        search_lower = search.strip().lower() if search else ""
        cat_lower = category_filter.strip().lower() if category_filter else ""

        filtered_apps = []
        for app in raw_apps:
            name = app['app_name']
            cat = config.get_category_for_app(name)
            app['category'] = cat
            app['percentage'] = self._pct(app['total_duration'], total_time)
            sc = max(app['sessions_count'], 1)
            app['avg_session'] = int(app['total_duration'] / sc)
            app['avg_session_formatted'] = self._format_duration(app['avg_session'])
            app['longest_session_formatted'] = self._format_duration(app['longest_session'])
            app['last_used_label'] = datetime.fromtimestamp(app['last_used']).strftime('%d/%m %H:%M') if app['last_used'] else '-'

            if search_lower and search_lower not in name.lower():
                continue
            if cat_lower and cat.lower() != cat_lower:
                continue
            filtered_apps.append(app)

        return filtered_apps

    def get_app_details(self, app_name, start_ts, end_ts):
        segments = self._segments(start_ts, end_ts)
        app_segments = [s for s in segments if s['app_name'] == app_name]
        active_segments = [s for s in app_segments if s['status'] != 'idle']
        total = sum(s['duration'] for s in active_segments)
        total_all = self._status_totals(start_ts, end_ts)['active']

        sessions, _, _ = self._build_sessions(segments)
        app_sessions = [s for s in sessions if s['app_name'] == app_name]
        meaningful = [s for s in app_sessions if s['duration'] >= 10]
        longest = max(app_sessions, key=lambda s: s['duration']) if app_sessions else None

        hourly = [0] * 24
        daily = {}
        titles = {}
        fullscreen = 0
        for s in active_segments:
            dt = datetime.fromtimestamp(s['start'])
            hourly[dt.hour] += s['duration']
            day = dt.strftime('%Y-%m-%d')
            daily[day] = daily.get(day, 0) + s['duration']
            title = (s['window_title'] or '').strip() or '(sans titre)'
            titles[title] = titles.get(title, 0) + s['duration']
            if s['status'] == 'fullscreen':
                fullscreen += s['duration']

        top_titles = sorted(titles.items(), key=lambda kv: kv[1], reverse=True)[:15]

        first_last = self._query('''
            SELECT MIN(timestamp) AS first_ts, MAX(COALESCE(end_timestamp, timestamp + duration)) AS last_ts
            FROM raw_logs WHERE app_name = ?
        ''', (app_name,))
        first_ts = first_last[0]['first_ts'] if first_last else None
        last_ts = first_last[0]['last_ts'] if first_last else None

        days_used = len(daily)
        return {
            "app_name": app_name,
            "category": config.get_category_for_app(app_name),
            "total_duration": total,
            "formatted_total": self._format_duration(total),
            "percentage_of_total": self._pct(total, total_all),
            "fullscreen_duration": fullscreen,
            "fullscreen_formatted": self._format_duration(fullscreen),
            "sessions_count": len(meaningful),
            "avg_session_formatted": self._format_duration(
                int(sum(s['duration'] for s in meaningful) / len(meaningful)) if meaningful else 0),
            "longest_session": self._session_to_dict(longest) if longest else None,
            "days_used": days_used,
            "daily_average_formatted": self._format_duration(int(total / days_used) if days_used else 0),
            "first_seen": datetime.fromtimestamp(first_ts).strftime('%d/%m/%Y %H:%M') if first_ts else '-',
            "last_seen": datetime.fromtimestamp(last_ts).strftime('%d/%m/%Y %H:%M') if last_ts else '-',
            "hourly": [{"hour": h, "duration": d} for h, d in enumerate(hourly)],
            "daily": [{"date_str": d, "duration": v, "formatted": self._format_duration(v)}
                      for d, v in sorted(daily.items())],
            "top_titles": [{"title": t, "duration": d, "formatted": self._format_duration(d),
                            "percentage": self._pct(d, total)} for t, d in top_titles],
        }

    # ------------------------------------------------------------------ day timeline

    def get_day_timeline(self, day_start_ts, day_end_ts):
        segments = self._segments(day_start_ts, day_end_ts)
        focus, sessions = self._focus_stats(segments)
        totals = self._status_totals(day_start_ts, day_end_ts)

        # Blocks for the 24h strip: merge contiguous segments of the same app / status.
        blocks = []
        gap = self._session_gap()
        for seg in segments:
            kind = 'idle' if seg['status'] == 'idle' else 'active'
            last = blocks[-1] if blocks else None
            if (last and last['kind'] == kind and last['app_name'] == seg['app_name']
                    and seg['start'] - last['end'] <= gap):
                last['end'] = max(last['end'], seg['end'])
                last['duration'] += seg['duration']
            else:
                blocks.append({
                    "kind": kind,
                    "app_name": seg['app_name'],
                    "start": seg['start'],
                    "end": seg['end'],
                    "duration": seg['duration'],
                })
        for b in blocks:
            b['category'] = 'Inactif' if b['kind'] == 'idle' else config.get_category_for_app(b['app_name'])
            b['start_min'] = (b['start'] - day_start_ts) / 60.0
            b['end_min'] = (b['end'] - day_start_ts) / 60.0
            b['start_label'] = datetime.fromtimestamp(b['start']).strftime('%H:%M')
            b['end_label'] = datetime.fromtimestamp(b['end']).strftime('%H:%M')
            b['formatted'] = self._format_duration(b['duration'])

        active_segments = [s for s in segments if s['status'] != 'idle']
        first_ts = min((s['start'] for s in active_segments), default=None)
        last_ts = max((s['end'] for s in active_segments), default=None)

        apps = {}
        cats = {}
        for s in active_segments:
            apps[s['app_name']] = apps.get(s['app_name'], 0) + s['duration']
            cat = config.get_category_for_app(s['app_name'])
            cats[cat] = cats.get(cat, 0) + s['duration']

        session_list = [self._session_to_dict(s) for s in sessions if s['duration'] >= 60]

        return {
            "total_active": totals['active'],
            "total_active_formatted": self._format_duration(totals['active']),
            "total_idle_formatted": self._format_duration(totals['idle']),
            "first_activity": datetime.fromtimestamp(first_ts).strftime('%H:%M') if first_ts else '-',
            "last_activity": datetime.fromtimestamp(last_ts).strftime('%H:%M') if last_ts else '-',
            "span_formatted": self._format_duration(last_ts - first_ts) if first_ts else '-',
            "focus": focus,
            "blocks": blocks,
            "sessions": session_list,
            "top_apps": [{"app_name": a, "category": config.get_category_for_app(a), "duration": d,
                          "formatted": self._format_duration(d), "percentage": self._pct(d, totals['active'])}
                         for a, d in sorted(apps.items(), key=lambda kv: kv[1], reverse=True)[:8]],
            "categories": [{"category": c, "duration": d, "formatted": self._format_duration(d),
                            "percentage": self._pct(d, totals['active'])}
                           for c, d in sorted(cats.items(), key=lambda kv: kv[1], reverse=True)],
        }

    # ------------------------------------------------------------------ heatmap

    def get_heatmap_data(self, start_ts, end_ts):
        return self._query(f'''
            SELECT
                strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) AS weekday, -- 0=Sunday
                strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) AS hour,
                SUM(duration) AS duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND {ACTIVE_SQL}
            GROUP BY weekday, hour
        ''', (start_ts, end_ts))

    # ------------------------------------------------------------------ analytics

    def get_advanced_analytics(self, start_ts, end_ts, prev_start_ts=None, prev_end_ts=None):
        totals = self._status_totals(start_ts, end_ts)
        total_active = totals['active']
        total_idle = totals['idle']

        has_prev = prev_start_ts is not None and prev_end_ts is not None
        total_prev_active = self._status_totals(prev_start_ts, prev_end_ts)['active'] if has_prev else 0
        active_pct_change = self._pct_change(total_active, total_prev_active)

        # 1. Hourly distribution & day quadrants
        hourly_rows = {r['hour']: r['duration'] for r in self._query(f'''
            SELECT CAST(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) AS INTEGER) AS hour,
                   SUM(duration) AS duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND {ACTIVE_SQL}
            GROUP BY hour
        ''', (start_ts, end_ts))}

        hourly_distribution = []
        peak_hour = None
        peak_hour_duration = 0
        quadrants = {"nuit": 0, "matin": 0, "apres_midi": 0, "soiree": 0}
        for h in range(24):
            dur = hourly_rows.get(h, 0)
            hourly_distribution.append({"hour": h, "label": f"{h}h", "duration": dur,
                                        "formatted": self._format_duration(dur)})
            if dur > peak_hour_duration:
                peak_hour_duration = dur
                peak_hour = h
            if h < 6:
                quadrants["nuit"] += dur
            elif h < 12:
                quadrants["matin"] += dur
            elif h < 18:
                quadrants["apres_midi"] += dur
            else:
                quadrants["soiree"] += dur

        dominant_quadrant = max(quadrants, key=quadrants.get) if total_active > 0 else None
        quadrant_labels = {
            "nuit": "Nuit (00h - 06h)",
            "matin": "Matin (06h - 12h)",
            "apres_midi": "Après-midi (12h - 18h)",
            "soiree": "Soirée (18h - 24h)",
        }

        # 2. Weekdays
        weekday_rows = {r['weekday']: r for r in self._query(f'''
            SELECT CAST(strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) AS INTEGER) AS weekday,
                   SUM(duration) AS total_duration,
                   COUNT(DISTINCT strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime'))) AS day_count
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND {ACTIVE_SQL}
            GROUP BY weekday
        ''', (start_ts, end_ts))}

        day_mapping = [(1, "Lundi", "Lun"), (2, "Mardi", "Mar"), (3, "Mercredi", "Mer"), (4, "Jeudi", "Jeu"),
                       (5, "Vendredi", "Ven"), (6, "Samedi", "Sam"), (0, "Dimanche", "Dim")]
        weekdays_distribution = []
        peak_weekday = None
        max_avg_day_duration = 0
        weekday_total = 0
        weekend_total = 0
        for w_id, full_name, short_name in day_mapping:
            row_data = weekday_rows.get(w_id)
            dur = row_data['total_duration'] if row_data else 0
            day_cnt = row_data['day_count'] if row_data else 0
            avg_dur = int(dur / day_cnt) if day_cnt > 0 else 0
            if w_id in (1, 2, 3, 4, 5):
                weekday_total += dur
            else:
                weekend_total += dur
            if avg_dur > max_avg_day_duration:
                max_avg_day_duration = avg_dur
                peak_weekday = full_name
            weekdays_distribution.append({
                "weekday": w_id, "name": full_name, "short": short_name,
                "total_duration": dur, "avg_duration": avg_dur, "day_count": day_cnt,
                "formatted_avg": self._format_duration(avg_dur),
                "formatted_total": self._format_duration(dur),
            })

        # 3. Daily series, peak day & streak
        time_series = self._query(f'''
            SELECT strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) AS date_str,
                   SUM(duration) AS duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND {ACTIVE_SQL}
            GROUP BY date_str
            ORDER BY date_str ASC
        ''', (start_ts, end_ts))
        for pt in time_series:
            pt['formatted'] = self._format_duration(pt['duration'])

        peak_day = None
        if time_series:
            best = max(time_series, key=lambda p: p['duration'])
            top_app = self._query(f'''
                SELECT app_name, SUM(duration) AS dur FROM raw_logs
                WHERE strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) = ? AND {ACTIVE_SQL}
                GROUP BY app_name ORDER BY dur DESC LIMIT 1
            ''', (best['date_str'],))
            peak_day = {
                "date": best['date_str'],
                "duration": best['duration'],
                "formatted": best['formatted'],
                "top_app": top_app[0]['app_name'] if top_app else "-",
            }

        active_dates = [r['d'] for r in self._query(f'''
            SELECT DISTINCT strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) AS d
            FROM raw_logs WHERE {ACTIVE_SQL}
        ''')]
        streak = self._calculate_streak(active_dates)
        active_days_count = len(time_series)

        # 4. Apps & trends vs previous period
        curr_apps = self._app_totals(start_ts, end_ts)
        prev_apps_map = {}
        if has_prev:
            prev_apps_map = {r['app_name']: r['total_duration'] for r in self._app_totals(prev_start_ts, prev_end_ts)}

        top_apps_trends = []
        for app in curr_apps:
            name = app['app_name']
            dur = app['total_duration']
            prev_dur = prev_apps_map.get(name, 0)
            if prev_dur > 0:
                diff = dur - prev_dur
                pct = round((diff / prev_dur) * 100, 1)
                trend = 'up' if pct > 5 else ('down' if pct < -5 else 'stable')
            else:
                diff = dur
                pct = None
                trend = 'new' if (has_prev and total_prev_active > 0) else 'stable'
            top_apps_trends.append({
                "app_name": name,
                "category": config.get_category_for_app(name),
                "current_duration": dur,
                "prev_duration": prev_dur,
                "diff_duration": diff,
                "pct_change": pct,
                "trend": trend,
                "formatted_current": self._format_duration(dur),
                "formatted_diff": ("+" if diff > 0 else "-") + self._format_duration(abs(diff)),
                "percentage_of_total": self._pct(dur, total_active),
            })

        # 5. Categories & productivity
        categories_dict = {}
        productive_dur = entertainment_dur = communication_dur = neutral_dur = 0
        for app in curr_apps:
            dur = app['total_duration']
            cat = config.get_category_for_app(app['app_name'])
            prod_type = config.get_productivity_type(cat)
            if prod_type == 'productive':
                productive_dur += dur
            elif prod_type == 'entertainment':
                entertainment_dur += dur
            elif prod_type == 'communication':
                communication_dur += dur
            else:
                neutral_dur += dur
            entry = categories_dict.setdefault(cat, {"category": cat, "duration": 0, "type": prod_type, "apps": []})
            entry["duration"] += dur
            entry["apps"].append({"app_name": app['app_name'], "duration": dur,
                                  "formatted": self._format_duration(dur)})

        sorted_categories = sorted(categories_dict.values(), key=lambda x: x["duration"], reverse=True)
        for cat in sorted_categories:
            cat["percentage"] = self._pct(cat["duration"], total_active)
            cat["formatted"] = self._format_duration(cat["duration"])
            cat["apps"] = sorted(cat["apps"], key=lambda x: x["duration"], reverse=True)[:3]

        prod_base = productive_dur + entertainment_dur
        if prod_base > 0:
            productivity_score = round((productive_dur / prod_base) * 100)
        elif total_active > 0:
            productivity_score = 50
        else:
            productivity_score = 0

        # 6. Category evolution per day (stacked chart)
        per_day_app = self._query(f'''
            SELECT strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) AS d,
                   app_name, SUM(duration) AS dur
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND {ACTIVE_SQL}
            GROUP BY d, app_name
        ''', (start_ts, end_ts))
        dates = [p['date_str'] for p in time_series]
        date_idx = {d: i for i, d in enumerate(dates)}
        cat_series = {}
        for r in per_day_app:
            cat = config.get_category_for_app(r['app_name'])
            values = cat_series.setdefault(cat, [0] * len(dates))
            if r['d'] in date_idx:
                values[date_idx[r['d']]] += r['dur']
        category_evolution = {
            "dates": dates,
            "series": [{"category": c, "values": v}
                       for c, v in sorted(cat_series.items(), key=lambda kv: sum(kv[1]), reverse=True)],
        }

        # 7. Focus, sessions & rhythm
        focus, _ = self._focus_stats(self._segments(start_ts, end_ts))
        rhythm = self._daily_rhythm(start_ts, end_ts)

        num_days = max(1, active_days_count)
        daily_average = int(total_active / num_days) if total_active > 0 else 0

        return {
            "total_active": total_active,
            "total_idle": total_idle,
            "total_fullscreen": totals['fullscreen'],
            "total_active_formatted": self._format_duration(total_active),
            "total_idle_formatted": self._format_duration(total_idle),
            "total_fullscreen_formatted": self._format_duration(totals['fullscreen']),
            "prev_total_active": total_prev_active if has_prev else None,
            "prev_total_active_formatted": self._format_duration(total_prev_active) if has_prev else "-",
            "active_pct_change": active_pct_change,
            "daily_average": daily_average,
            "daily_average_formatted": self._format_duration(daily_average),
            "active_days_count": active_days_count,
            "streak": streak,
            "peak_hour": peak_hour,
            "peak_hour_label": f"{peak_hour}h - {peak_hour + 1}h" if peak_hour is not None else "-",
            "peak_hour_duration": peak_hour_duration,
            "peak_hour_formatted": self._format_duration(peak_hour_duration),
            "hourly_distribution": hourly_distribution,
            "quadrants": {
                "dominant": dominant_quadrant,
                "dominant_label": quadrant_labels.get(dominant_quadrant, "-"),
                "values": quadrants,
                "percentages": {k: self._pct(v, total_active) for k, v in quadrants.items()},
            },
            "peak_weekday": peak_weekday or "-",
            "max_avg_day_duration": max_avg_day_duration,
            "max_avg_day_formatted": self._format_duration(max_avg_day_duration),
            "weekdays_distribution": weekdays_distribution,
            "weekday_split": {
                "weekday_total": weekday_total,
                "weekend_total": weekend_total,
                "weekday_pct": self._pct(weekday_total, total_active),
                "weekend_pct": self._pct(weekend_total, total_active),
            },
            "peak_day": peak_day,
            "time_series": time_series,
            "top_apps_trends": top_apps_trends,
            "categories": sorted_categories,
            "category_evolution": category_evolution,
            "dominant_category": sorted_categories[0]["category"] if sorted_categories else "-",
            "productivity_score": productivity_score,
            "productive_time_formatted": self._format_duration(productive_dur),
            "entertainment_time_formatted": self._format_duration(entertainment_dur),
            "communication_time_formatted": self._format_duration(communication_dur),
            "neutral_time_formatted": self._format_duration(neutral_dur),
            "focus": focus,
            "switches_per_hour": focus['switches_per_hour'],
            "focus_label": focus['focus_label'],
            "focus_status": focus['focus_status'],
            "rhythm": rhythm,
        }


db = DatabaseManager()
