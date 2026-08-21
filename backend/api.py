from .db import db
from .config import config
import time
from datetime import datetime, timedelta

class Api:
    def __init__(self):
        pass

    def get_dashboard_data(self, period='today'):
        now = datetime.now()
        
        if period == 'today':
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif period == 'week':
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end = (start + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
        elif period == 'month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            # handle end of month simple logic
            next_month = start.replace(month=start.month+1) if start.month < 12 else start.replace(year=start.year+1, month=1)
            end = next_month - timedelta(seconds=1)
        else:
            # fallback today
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        start_ts = int(start.timestamp())
        end_ts = int(end.timestamp())
        
        return db.get_dashboard_stats(start_ts, end_ts)

    def get_all_apps(self, period='today'):
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        
        if period == 'week':
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end = (start + timedelta(days=6, hours=23, minutes=59, seconds=59))
        
        return db.get_all_apps_stats(int(start.timestamp()), int(end.timestamp()))

    def get_heatmap(self, period='week'):
        now = datetime.now()
        start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = (start + timedelta(days=6, hours=23, minutes=59, seconds=59))
        return db.get_heatmap_data(int(start.timestamp()), int(end.timestamp()))

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
