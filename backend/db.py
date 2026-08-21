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
        
        # Decorate top apps with categories
        for app in top_apps:
            app['category'] = config.get_category_for_app(app['app_name'])
        
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
        
        return {
            "total_active": total_active,
            "total_idle": total_idle,
            "top_apps": top_apps,
            "timeline": timeline
        }

    def get_all_apps_stats(self, start_ts, end_ts):
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT app_name, SUM(duration) as total_duration
            FROM raw_logs
            WHERE timestamp >= ? AND timestamp <= ? AND (status = 'active' OR status = 'fullscreen')
            GROUP BY app_name
            ORDER BY total_duration DESC
        ''', (start_ts, end_ts))
        apps = [dict(row) for row in cursor.fetchall()]
        for app in apps:
            app['category'] = config.get_category_for_app(app['app_name'])
        return apps

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

    def purge_old_data(self, days):
        """Delete records older than `days`."""
        cursor = self.conn.cursor()
        threshold_ts = int(time.time()) - (days * 86400)
        cursor.execute('''
            DELETE FROM raw_logs WHERE timestamp < ?
        ''', (threshold_ts,))
        self.conn.commit()

db = DatabaseManager()
