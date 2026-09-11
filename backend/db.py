import sqlite3
import os
import time
from datetime import datetime, timedelta
from .config import APP_DATA_DIR, config

DB_FILE = os.path.join(APP_DATA_DIR, 'trackr.db')

class DatabaseManager:
    def __init__(self):
        self.conn = sqlite3.connect(DB_FILE, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cursor = self.conn.cursor()
        
        # Table for raw tracking events
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS raw_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp INTEGER NOT NULL,
                app_name TEXT NOT NULL,
                window_title TEXT,
                status TEXT NOT NULL, -- 'active', 'idle', 'fullscreen'
                duration INTEGER NOT NULL
            )
        ''')
        
        # Create indexes for faster queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_timestamp ON raw_logs(timestamp)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_app_name ON raw_logs(app_name)')
        
        self.conn.commit()

    def insert_log(self, app_name, window_title, status, duration):
        if duration <= 0:
            return
            
        cursor = self.conn.cursor()
        timestamp = int(time.time())
        cursor.execute('''
            INSERT INTO raw_logs (timestamp, app_name, window_title, status, duration)
            VALUES (?, ?, ?, ?, ?)
        ''', (timestamp, app_name, window_title, status, duration))
        self.conn.commit()

    def _format_duration(self, seconds):
        if not seconds or seconds <= 0:
            return "0m"
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        if h > 0:
            return f"{h}h {m:02d}m" if m > 0 else f"{h}h"
        return f"{m}m"

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

    def get_dashboard_stats(self, start_ts, end_ts):
        """Returns statistics for a given time range."""
        cursor = self.conn.cursor()
        
        # 1. Total screen time (active + fullscreen)
        cursor.execute('''
            SELECT SUM(duration) as total 
            FROM raw_logs 
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
        ''', (start_ts, end_ts))
        total_active_row = cursor.fetchone()
        total_active = total_active_row['total'] if total_active_row and total_active_row['total'] else 0
        
        # 2. Total idle time
        cursor.execute('''
            SELECT SUM(duration) as total 
            FROM raw_logs 
            WHERE timestamp >= ? AND timestamp <= ? AND status = 'idle'
        ''', (start_ts, end_ts))
        total_idle_row = cursor.fetchone()
        total_idle = total_idle_row['total'] if total_idle_row and total_idle_row['total'] else 0
        
        # 3. Top Applications
        cursor.execute('''
            SELECT app_name, SUM(duration) as total_duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY app_name
            ORDER BY total_duration DESC
            LIMIT 5
        ''', (start_ts, end_ts))
        top_apps = [dict(row) for row in cursor.fetchall()]
        
        # Decorate top apps with categories and percentage
        for app in top_apps:
            app['category'] = config.get_category_for_app(app['app_name'])
            app['percentage'] = round((app['total_duration'] / total_active) * 100, 1) if total_active > 0 else 0
        
        # 4. Timeline data (grouped by hour for the chart)
        cursor.execute('''
            SELECT 
                strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as hour,
                SUM(duration) as duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY hour
            ORDER BY hour ASC
        ''', (start_ts, end_ts))
        timeline = [dict(row) for row in cursor.fetchall()]
        
        peak_hour = None
        max_hour_dur = 0
        for item in timeline:
            if item['duration'] > max_hour_dur:
                max_hour_dur = item['duration']
                peak_hour = int(item['hour'])

        # 5. Category breakdown for dashboard
        cursor.execute('''
            SELECT app_name, SUM(duration) as total_duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY app_name
        ''', (start_ts, end_ts))
        cat_map = {}
        for row in cursor.fetchall():
            cat = config.get_category_for_app(row['app_name'])
            cat_map[cat] = cat_map.get(cat, 0) + row['total_duration']
            
        top_categories = sorted(
            [{"category": k, "duration": v, "percentage": round((v / total_active) * 100, 1) if total_active > 0 else 0} 
             for k, v in cat_map.items()],
            key=lambda x: x["duration"],
            reverse=True
        )[:4]
        
        return {
            "total_active": total_active,
            "total_idle": total_idle,
            "top_apps": top_apps,
            "timeline": timeline,
            "peak_hour": peak_hour,
            "top_categories": top_categories
        }

    def get_all_apps_stats(self, start_ts, end_ts, search="", category_filter=""):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT app_name, SUM(duration) as total_duration, COUNT(*) as sessions_count
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY app_name
            ORDER BY total_duration DESC
        ''', (start_ts, end_ts))
        raw_apps = [dict(row) for row in cursor.fetchall()]
        
        total_time = sum(a['total_duration'] for a in raw_apps)
        filtered_apps = []
        
        search_lower = search.strip().lower() if search else ""
        cat_lower = category_filter.strip().lower() if category_filter else ""
        
        for app in raw_apps:
            name = app['app_name']
            cat = config.get_category_for_app(name)
            app['category'] = cat
            app['percentage'] = round((app['total_duration'] / total_time) * 100, 1) if total_time > 0 else 0
            
            # Search filter
            if search_lower and search_lower not in name.lower():
                continue
            # Category filter
            if cat_lower and cat.lower() != cat_lower:
                continue
                
            filtered_apps.append(app)
            
        return filtered_apps

    def get_heatmap_data(self, start_ts, end_ts):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT 
                strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) as weekday, -- 0=Sunday
                strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) as hour,
                SUM(duration) as duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY weekday, hour
        ''', (start_ts, end_ts))
        return [dict(row) for row in cursor.fetchall()]

    def get_advanced_analytics(self, start_ts, end_ts, prev_start_ts=None, prev_end_ts=None):
        cursor = self.conn.cursor()
        
        # 1. Total Screen Time (Current Period)
        cursor.execute('''
            SELECT SUM(duration) as total 
            FROM raw_logs 
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
        ''', (start_ts, end_ts))
        row = cursor.fetchone()
        total_active = row['total'] if row and row['total'] else 0
        
        cursor.execute('''
            SELECT SUM(duration) as total 
            FROM raw_logs 
            WHERE timestamp >= ? AND timestamp <= ? AND status = 'idle'
        ''', (start_ts, end_ts))
        row = cursor.fetchone()
        total_idle = row['total'] if row and row['total'] else 0
        
        # Total Previous Period (for overall comparison)
        total_prev_active = 0
        if prev_start_ts is not None and prev_end_ts is not None:
            cursor.execute('''
                SELECT SUM(duration) as total 
                FROM raw_logs 
                WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            ''', (prev_start_ts, prev_end_ts))
            row = cursor.fetchone()
            total_prev_active = row['total'] if row and row['total'] else 0

        if total_prev_active > 0:
            active_pct_change = round(((total_active - total_prev_active) / total_prev_active) * 100, 1)
        else:
            active_pct_change = 0 if total_active == 0 else 100

        # 2. Hourly Distribution & Peak Hours
        cursor.execute('''
            SELECT 
                CAST(strftime('%H', datetime(timestamp, 'unixepoch', 'localtime')) AS INTEGER) as hour,
                SUM(duration) as duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY hour
            ORDER BY hour ASC
        ''', (start_ts, end_ts))
        hourly_rows = {row['hour']: row['duration'] for row in cursor.fetchall()}
        
        hourly_distribution = []
        peak_hour = None
        peak_hour_duration = 0
        
        quadrants = {
            "nuit": 0,      # 00h - 06h
            "matin": 0,     # 06h - 12h
            "apres_midi": 0,# 12h - 18h
            "soiree": 0     # 18h - 24h
        }
        
        for h in range(24):
            dur = hourly_rows.get(h, 0)
            hourly_distribution.append({
                "hour": h,
                "label": f"{h}h",
                "duration": dur,
                "formatted": self._format_duration(dur)
            })
            if dur > peak_hour_duration:
                peak_hour_duration = dur
                peak_hour = h
                
            if 0 <= h < 6:
                quadrants["nuit"] += dur
            elif 6 <= h < 12:
                quadrants["matin"] += dur
            elif 12 <= h < 18:
                quadrants["apres_midi"] += dur
            else:
                quadrants["soiree"] += dur

        dominant_quadrant = max(quadrants, key=quadrants.get) if total_active > 0 else "apres_midi"
        quadrant_labels = {
            "nuit": "Nuit (00h - 06h)",
            "matin": "Matin (06h - 12h)",
            "apres_midi": "Après-midi (12h - 18h)",
            "soiree": "Soirée (18h - 24h)"
        }

        # 3. Peak Weekdays
        cursor.execute('''
            SELECT 
                CAST(strftime('%w', datetime(timestamp, 'unixepoch', 'localtime')) AS INTEGER) as weekday,
                SUM(duration) as total_duration,
                COUNT(DISTINCT strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime'))) as day_count
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY weekday
        ''', (start_ts, end_ts))
        weekday_rows = {row['weekday']: row for row in cursor.fetchall()}
        
        day_mapping = [
            (1, "Lundi", "Lun"),
            (2, "Mardi", "Mar"),
            (3, "Mercredi", "Mer"),
            (4, "Jeudi", "Jeu"),
            (5, "Vendredi", "Ven"),
            (6, "Samedi", "Sam"),
            (0, "Dimanche", "Dim")
        ]
        
        weekdays_distribution = []
        peak_weekday = None
        max_avg_day_duration = 0
        weekday_total = 0
        weekend_total = 0
        
        for w_id, full_name, short_name in day_mapping:
            row_data = weekday_rows.get(w_id, None)
            dur = row_data['total_duration'] if row_data else 0
            day_cnt = row_data['day_count'] if row_data else 0
            avg_dur = int(dur / day_cnt) if day_cnt > 0 else dur
            
            if w_id in [1, 2, 3, 4, 5]:
                weekday_total += dur
            else:
                weekend_total += dur
                
            if avg_dur > max_avg_day_duration:
                max_avg_day_duration = avg_dur
                peak_weekday = full_name
                
            weekdays_distribution.append({
                "weekday": w_id,
                "name": full_name,
                "short": short_name,
                "total_duration": dur,
                "avg_duration": avg_dur,
                "day_count": day_cnt,
                "formatted_avg": self._format_duration(avg_dur),
                "formatted_total": self._format_duration(dur)
            })

        # 4. Peaks & Records
        # Period Peak Day
        cursor.execute('''
            SELECT 
                strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) as day_date,
                SUM(duration) as day_duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY day_date
            ORDER BY day_duration DESC
            LIMIT 1
        ''', (start_ts, end_ts))
        peak_day_row = cursor.fetchone()
        peak_day = None
        if peak_day_row:
            p_date = peak_day_row['day_date']
            p_dur = peak_day_row['day_duration']
            cursor.execute('''
                SELECT app_name, SUM(duration) as dur
                FROM raw_logs
                WHERE strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) = ?
                  AND (status = 'active' OR status = 'fullscreen')
                GROUP BY app_name
                ORDER BY dur DESC
                LIMIT 1
            ''', (p_date,))
            top_app_day = cursor.fetchone()
            peak_day = {
                "date": p_date,
                "duration": p_dur,
                "formatted": self._format_duration(p_dur),
                "top_app": top_app_day['app_name'] if top_app_day else "-"
            }

        # All-Time Record Day
        cursor.execute('''
            SELECT 
                strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) as day_date,
                SUM(duration) as day_duration
            FROM raw_logs
            WHERE (status = 'active' OR status = 'fullscreen')
            GROUP BY day_date
            ORDER BY day_duration DESC
            LIMIT 1
        ''')
        all_time_row = cursor.fetchone()
        all_time_peak_day = None
        if all_time_row:
            at_date = all_time_row['day_date']
            at_dur = all_time_row['day_duration']
            cursor.execute('''
                SELECT app_name, SUM(duration) as dur
                FROM raw_logs
                WHERE strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) = ?
                  AND (status = 'active' OR status = 'fullscreen')
                GROUP BY app_name
                ORDER BY dur DESC
                LIMIT 1
            ''', (at_date,))
            at_app = cursor.fetchone()
            all_time_peak_day = {
                "date": at_date,
                "duration": at_dur,
                "formatted": self._format_duration(at_dur),
                "top_app": at_app['app_name'] if at_app else "-"
            }

        # Daily time-series for plotting spikes
        cursor.execute('''
            SELECT 
                strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) as date_str,
                SUM(duration) as duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY date_str
            ORDER BY date_str ASC
        ''', (start_ts, end_ts))
        time_series = [dict(row) for row in cursor.fetchall()]
        for pt in time_series:
            pt['formatted'] = self._format_duration(pt['duration'])

        # Streaks
        cursor.execute('''
            SELECT DISTINCT strftime('%Y-%m-%d', datetime(timestamp, 'unixepoch', 'localtime')) as active_date
            FROM raw_logs
            WHERE (status = 'active' OR status = 'fullscreen')
            ORDER BY active_date DESC
        ''')
        active_dates = [r['active_date'] for r in cursor.fetchall()]
        active_days_count = len(time_series)
        streak = self._calculate_streak(active_dates)

        # 5. Apps & Trends (Comparison with previous period)
        cursor.execute('''
            SELECT app_name, SUM(duration) as total_duration, COUNT(*) as session_entries
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY app_name
            ORDER BY total_duration DESC
        ''', (start_ts, end_ts))
        curr_apps = [dict(row) for row in cursor.fetchall()]
        
        prev_apps_map = {}
        if prev_start_ts is not None and prev_end_ts is not None:
            cursor.execute('''
                SELECT app_name, SUM(duration) as total_duration
                FROM raw_logs
                WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
                GROUP BY app_name
            ''', (prev_start_ts, prev_end_ts))
            prev_apps_map = {row['app_name']: row['total_duration'] for row in cursor.fetchall()}

        top_apps_trends = []
        for app in curr_apps:
            name = app['app_name']
            dur = app['total_duration']
            cat = config.get_category_for_app(name)
            prev_dur = prev_apps_map.get(name, 0)
            
            if prev_dur > 0:
                diff = dur - prev_dur
                pct = round((diff / prev_dur) * 100, 1)
                trend = 'up' if pct > 5 else ('down' if pct < -5 else 'stable')
            else:
                diff = dur
                pct = 100.0 if dur > 0 else 0
                trend = 'new' if (prev_start_ts is not None and total_prev_active > 0) else 'stable'

            top_apps_trends.append({
                "app_name": name,
                "category": cat,
                "current_duration": dur,
                "prev_duration": prev_dur,
                "diff_duration": diff,
                "pct_change": pct,
                "trend": trend,
                "formatted_current": self._format_duration(dur),
                "formatted_diff": ("+" if diff > 0 else "") + self._format_duration(abs(diff)),
                "percentage_of_total": round((dur / total_active) * 100, 1) if total_active > 0 else 0,
                "sessions": app['session_entries']
            })

        # 6. Categories Breakdown & Productivity Score
        categories_dict = {}
        productive_dur = 0
        entertainment_dur = 0
        neutral_dur = 0
        
        for app in curr_apps:
            dur = app['total_duration']
            cat = config.get_category_for_app(app['app_name'])
            prod_type = config.get_productivity_type(cat)
            
            if prod_type == 'productive':
                productive_dur += dur
            elif prod_type == 'entertainment':
                entertainment_dur += dur
            else:
                neutral_dur += dur
                
            if cat not in categories_dict:
                categories_dict[cat] = {
                    "category": cat,
                    "duration": 0,
                    "type": prod_type,
                    "apps": []
                }
            categories_dict[cat]["duration"] += dur
            categories_dict[cat]["apps"].append({
                "app_name": app['app_name'],
                "duration": dur,
                "formatted": self._format_duration(dur)
            })

        sorted_categories = sorted(categories_dict.values(), key=lambda x: x["duration"], reverse=True)
        for cat in sorted_categories:
            cat["percentage"] = round((cat["duration"] / total_active) * 100, 1) if total_active > 0 else 0
            cat["formatted"] = self._format_duration(cat["duration"])
            cat["apps"] = sorted(cat["apps"], key=lambda x: x["duration"], reverse=True)[:3]

        prod_base = productive_dur + entertainment_dur
        if prod_base > 0:
            productivity_score = round((productive_dur / prod_base) * 100)
        elif total_active > 0:
            productivity_score = 50
        else:
            productivity_score = 0

        # 7. Focus & Fragmentation (App switch rate)
        cursor.execute('''
            SELECT COUNT(id) as total_switches
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
        ''', (start_ts, end_ts))
        switches_row = cursor.fetchone()
        raw_events = switches_row['total_switches'] if switches_row else 0
        active_hours = total_active / 3600.0
        switches_per_hour = round(raw_events / max(active_hours, 0.5), 1)
        
        if switches_per_hour < 15:
            focus_label = "Deep Work (Forte concentration)"
            focus_status = "excellent"
        elif switches_per_hour < 35:
            focus_label = "Concentration Modérée"
            focus_status = "good"
        else:
            focus_label = "Multitasking Élevé (Dispersion)"
            focus_status = "dispersed"

        num_days = max(1, len(time_series))
        daily_average = int(total_active / num_days) if total_active > 0 else 0

        return {
            "total_active": total_active,
            "total_idle": total_idle,
            "total_active_formatted": self._format_duration(total_active),
            "total_idle_formatted": self._format_duration(total_idle),
            "active_pct_change": active_pct_change,
            "daily_average": daily_average,
            "daily_average_formatted": self._format_duration(daily_average),
            "active_days_count": active_days_count,
            "streak": streak,
            # Peak Hours
            "peak_hour": peak_hour,
            "peak_hour_label": f"{peak_hour}h - {peak_hour+1}h" if peak_hour is not None else "-",
            "peak_hour_duration": peak_hour_duration,
            "peak_hour_formatted": self._format_duration(peak_hour_duration),
            "hourly_distribution": hourly_distribution,
            "quadrants": {
                "dominant": dominant_quadrant,
                "dominant_label": quadrant_labels.get(dominant_quadrant, "-"),
                "values": quadrants,
                "percentages": {
                    k: round((v / total_active) * 100, 1) if total_active > 0 else 0
                    for k, v in quadrants.items()
                }
            },
            # Peak Weekdays
            "peak_weekday": peak_weekday or "-",
            "max_avg_day_duration": max_avg_day_duration,
            "max_avg_day_formatted": self._format_duration(max_avg_day_duration),
            "weekdays_distribution": weekdays_distribution,
            "weekday_split": {
                "weekday_total": weekday_total,
                "weekend_total": weekend_total,
                "weekday_pct": round((weekday_total / total_active) * 100, 1) if total_active > 0 else 0,
                "weekend_pct": round((weekend_total / total_active) * 100, 1) if total_active > 0 else 0
            },
            # Peaks & Records
            "peak_day": peak_day,
            "all_time_peak_day": all_time_peak_day,
            "time_series": time_series,
            # Apps & Trends
            "top_apps_trends": top_apps_trends,
            # Categories
            "categories": sorted_categories,
            "dominant_category": sorted_categories[0]["category"] if sorted_categories else "-",
            "productivity_score": productivity_score,
            "productive_time_formatted": self._format_duration(productive_dur),
            "entertainment_time_formatted": self._format_duration(entertainment_dur),
            # Focus & Fragmentation
            "switches_per_hour": switches_per_hour,
            "focus_label": focus_label,
            "focus_status": focus_status
        }

    def purge_old_data(self, days):
        """Delete records older than `days`."""
        cursor = self.conn.cursor()
        threshold_ts = int(time.time()) - (days * 86400)
        cursor.execute('''
            DELETE FROM raw_logs WHERE timestamp < ?
        ''', (threshold_ts,))
        self.conn.commit()

db = DatabaseManager()
