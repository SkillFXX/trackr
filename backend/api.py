from .db import db
from .config import config
import time
from datetime import datetime, timedelta

class Api:
    def __init__(self):
        pass

    def _get_period_timestamps(self, period='today'):
        now = datetime.now()
        
        if period == 'today':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            # Previous: yesterday
            prev_start = start - timedelta(days=1)
            prev_end = end - timedelta(days=1)
        elif period == 'week':
            # Current week starting Monday
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end = (start + timedelta(days=6, hours=23, minutes=59, seconds=59, microseconds=999999))
            # Previous: last week
            prev_start = start - timedelta(days=7)
            prev_end = start - timedelta(microseconds=1)
        elif period == 'month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = start.replace(month=start.month+1) if start.month < 12 else start.replace(year=start.year+1, month=1)
            end = next_month - timedelta(microseconds=1)
            # Previous: last month
            prev_end = start - timedelta(microseconds=1)
            prev_start = prev_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif period == 'year':
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(month=12, day=31, hour=23, minute=59, second=59, microsecond=999999)
            # Previous: last year
            prev_start = start.replace(year=start.year - 1)
            prev_end = end.replace(year=end.year - 1)
        elif period == 'all':
            start = datetime(2020, 1, 1, 0, 0, 0)
            end = now + timedelta(days=1)
            prev_start = None
            prev_end = None
        else:
            # Fallback today
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            prev_start = start - timedelta(days=1)
            prev_end = end - timedelta(days=1)

        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())
        prev_start_ts = int(prev_start.timestamp()) if prev_start else None
        prev_end_ts = int(prev_end.timestamp()) if prev_end else None
        
        return start_ts, end_ts, prev_start_ts, prev_end_ts

    def get_dashboard_data(self, period='today'):
        start_ts, end_ts, _, _ = self._get_period_timestamps(period)
        return db.get_dashboard_stats(start_ts, end_ts)

    def get_advanced_analytics(self, period='week'):
        start_ts, end_ts, prev_start_ts, prev_end_ts = self._get_period_timestamps(period)
        return db.get_advanced_analytics(start_ts, end_ts, prev_start_ts, prev_end_ts)

    def get_all_apps(self, period='today', search='', category=''):
        start_ts, end_ts, _, _ = self._get_period_timestamps(period)
        return db.get_all_apps_stats(start_ts, end_ts, search, category)

    def set_app_category(self, app_name, category):
        config.set_app_category(app_name, category)
        return True

    def get_categories(self):
        cats = list(config.get("categories", {}).keys())
        # Make sure common categories exist in order
        default_order = [
            "Développement", "Navigation Web", "Jeux", "Communication", 
            "Productivité", "Multimédia & Musique", "Création & Design", 
            "Système & Utilitaires", "Non catégorisé"
        ]
        ordered_cats = [c for c in default_order if c in cats]
        for c in cats:
            if c not in ordered_cats:
                ordered_cats.append(c)
        if "Non catégorisé" not in ordered_cats:
            ordered_cats.append("Non catégorisé")
            
        return {
            "categories": ordered_cats,
            "app_overrides": config.get("app_overrides", {})
        }

    def get_heatmap(self, period='week'):
        start_ts, end_ts, _, _ = self._get_period_timestamps(period)
        return db.get_heatmap_data(start_ts, end_ts)

    def get_settings(self):
        return config.config

    def save_settings(self, new_settings):
        for k, v in new_settings.items():
            config.set(k, v)
        return True

    def export_csv(self):
        # To implement: trigger save dialog or save to Documents
        import csv
        import os
        from tkinter import filedialog
        import tkinter as tk
        
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        file_path = filedialog.asksaveasfilename(
            defaultextension=".csv", 
            filetypes=[("CSV Files", "*.csv")],
            title="Exporter les données"
        )
        
        if file_path:
            cursor = db.conn.cursor()
            cursor.execute("SELECT * FROM raw_logs ORDER BY timestamp ASC")
            rows = cursor.fetchall()
            
            with open(file_path, 'w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerow(['ID', 'Timestamp', 'App Name', 'Window Title', 'Status', 'Duration (s)'])
                for row in rows:
                    writer.writerow([row['id'], row['timestamp'], row['app_name'], row['window_title'], row['status'], row['duration']])
            return {"success": True, "path": file_path}
        return {"success": False, "error": "Cancelled"}
