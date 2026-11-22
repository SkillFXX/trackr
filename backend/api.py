from .db import db
from .config import config
import csv
from datetime import datetime, timedelta

# The pywebview window, set by main.py. Kept at module level on purpose:
# pywebview exposes every public attribute of the js_api object to JavaScript.
_window = None


def set_window(window):
    global _window
    _window = window


class Api:
    def _get_period_timestamps(self, period='today'):
        """Returns (start, end, prev_start, prev_end) timestamps.

        The previous period is cut at the same elapsed time as the current one
        (e.g. Monday -> Wednesday 15:00 is compared with last Monday -> last
        Wednesday 15:00) so that comparisons are fair while a period is running.
        """
        now = datetime.now()

        # Custom range: "custom:YYYY-MM-DD:YYYY-MM-DD" (both days included),
        # compared with the period of the same length just before it.
        if isinstance(period, str) and period.startswith('custom:'):
            try:
                _, first, last = period.split(':')
                start = datetime.strptime(first, '%Y-%m-%d')
                last_day = datetime.strptime(last, '%Y-%m-%d')
                if last_day < start:
                    start, last_day = last_day, start
                end = last_day + timedelta(days=1) - timedelta(microseconds=1)
                length = timedelta(days=(last_day - start).days + 1)
                prev_start = start - length
                # Range still running (ends today or later): cut the previous one at the same point
                elapsed = min(now, end) - start if now > start else length
                prev_end = min(prev_start + elapsed, start - timedelta(microseconds=1))
                return (int(start.timestamp()), int(end.timestamp()),
                        int(prev_start.timestamp()), int(prev_end.timestamp()))
            except ValueError:
                period = 'today'

        if period == 'week':
            start = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=7) - timedelta(microseconds=1)
            prev_start = start - timedelta(days=7)
        elif period == 'month':
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            next_month = start.replace(month=start.month + 1) if start.month < 12 else start.replace(year=start.year + 1, month=1)
            end = next_month - timedelta(microseconds=1)
            prev_start = (start - timedelta(days=1)).replace(day=1)
        elif period == 'year':
            start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
            end = start.replace(year=start.year + 1) - timedelta(microseconds=1)
            prev_start = start.replace(year=start.year - 1)
        elif period == 'all':
            start = datetime(2000, 1, 1)
            end = now + timedelta(days=1)
            prev_start = None
        else:  # today
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + timedelta(days=1) - timedelta(microseconds=1)
            prev_start = start - timedelta(days=1)

        prev_start_ts = prev_end_ts = None
        if prev_start is not None:
            elapsed = now - start
            prev_end = min(prev_start + elapsed, start - timedelta(microseconds=1))
            prev_start_ts = int(prev_start.timestamp())
            prev_end_ts = int(prev_end.timestamp())

        return int(start.timestamp()), int(end.timestamp()), prev_start_ts, prev_end_ts

    def get_dashboard_data(self, period='today'):
        return db.get_dashboard_stats(*self._get_period_timestamps(period))

    def get_advanced_analytics(self, period='week'):
        return db.get_advanced_analytics(*self._get_period_timestamps(period))

    def get_all_apps(self, period='today', search='', category=''):
        start_ts, end_ts, _, _ = self._get_period_timestamps(period)
        return db.get_all_apps_stats(start_ts, end_ts, search, category)

    def get_app_details(self, app_name, period='today'):
        start_ts, end_ts, _, _ = self._get_period_timestamps(period)
        return db.get_app_details(app_name, start_ts, end_ts)

    def get_day_timeline(self, date_str=None):
        try:
            day = datetime.strptime(date_str, '%Y-%m-%d') if date_str else datetime.now()
        except (TypeError, ValueError):
            day = datetime.now()
        start = day.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        data = db.get_day_timeline(int(start.timestamp()), int(end.timestamp()) - 1)
        data["date"] = start.strftime('%Y-%m-%d')
        data["is_today"] = start.date() == datetime.now().date()
        return data

    def set_app_category(self, app_name, category):
        config.set_app_category(app_name, category)
        return True

    def get_categories(self):
        cats = list(config.get("categories", {}).keys())
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

    def get_startup_status(self):
        return config.get_startup_status()

    def save_settings(self, new_settings):
        limits = {
            "refresh_interval": (1, 60),
            "idle_timeout": (10, 86400),
            "retention_days": (1, 3650),
        }
        clean = {}
        for k, v in (new_settings or {}).items():
            if k in limits:
                lo, hi = limits[k]
                try:
                    v = min(hi, max(lo, int(v)))
                except (TypeError, ValueError):
                    continue
            if k == "categories" and not isinstance(v, dict):
                continue
            clean[k] = v
        config.set_many(clean)
        if "retention_days" in clean:
            db.purge_old_data(clean["retention_days"])
        return {"success": True, "startup": config.get_startup_status()}

    def export_csv(self):
        if _window is None:
            return {"success": False, "error": "Fenêtre indisponible"}

        import webview
        save_dialog = getattr(getattr(webview, 'FileDialog', None), 'SAVE', None)
        if save_dialog is None:
            save_dialog = webview.SAVE_DIALOG

        result = _window.create_file_dialog(
            save_dialog,
            save_filename=f"trackr_{datetime.now().strftime('%Y-%m-%d')}.csv",
            file_types=('Fichiers CSV (*.csv)',),
        )
        if not result:
            return {"success": False, "error": "Cancelled"}
        file_path = result[0] if isinstance(result, (list, tuple)) else result
        if not file_path.lower().endswith('.csv'):
            file_path += '.csv'

        rows = db.export_rows()
        # utf-8-sig + ';' so that Excel (FR) opens the file correctly
        with open(file_path, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f, delimiter=';')
            writer.writerow(['ID', 'Début', 'Fin', 'Application', 'Catégorie', 'Titre de la fenêtre',
                             'Statut', 'Durée (s)'])
            for row in rows:
                end_ts = row.get('end_timestamp') or (row['timestamp'] + row['duration'])
                writer.writerow([
                    row['id'],
                    datetime.fromtimestamp(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                    datetime.fromtimestamp(end_ts).strftime('%Y-%m-%d %H:%M:%S'),
                    row['app_name'],
                    config.get_category_for_app(row['app_name']),
                    row['window_title'],
                    row['status'],
                    row['duration'],
                ])
        return {"success": True, "path": file_path}
