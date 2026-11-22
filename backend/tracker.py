import time
import threading
import win32gui
import win32process
import win32api
import psutil
from .db import db
from .config import config

# Processes shown while the session is locked: counted as idle time.
LOCK_SCREEN_PROCESSES = {"lockapp.exe", "logonui.exe"}

PURGE_EVERY = 6 * 3600  # seconds


class Tracker:
    def __init__(self):
        self.running = False
        self.thread = None
        self.interval = 5  # Check every 5 seconds
        self.last_check_time = time.time()
        self.last_purge_time = 0
        self._pid_names = {}

    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)

    def _get_idle_time(self):
        """Returns idle time in seconds."""
        last_input_info = win32api.GetLastInputInfo()
        current_tick = win32api.GetTickCount()
        # Both counters are 32-bit and wrap around every ~49.7 days.
        return ((current_tick - last_input_info) & 0xFFFFFFFF) / 1000.0

    def _process_name(self, pid):
        try:
            name = psutil.Process(pid).name()
        except (psutil.Error, ValueError):
            return self._pid_names.get(pid, "Unknown")
        if len(self._pid_names) > 500:
            self._pid_names.clear()
        self._pid_names[pid] = name
        return name

    def _get_active_window_info(self):
        """Returns (process_name, window_title, is_fullscreen)."""
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return "Unknown", "Unknown", False

        try:
            window_title = win32gui.GetWindowText(hwnd)
        except Exception:
            window_title = "Unknown"

        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process_name = self._process_name(pid)
        except Exception:
            process_name = "Unknown"

        # Fullscreen: the window covers the whole monitor it is displayed on.
        try:
            rect = win32gui.GetWindowRect(hwnd)
            monitor = win32api.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
            mon_rect = win32api.GetMonitorInfo(monitor)['Monitor']
            class_name = win32gui.GetClassName(hwnd)
            is_desktop = class_name in ("Progman", "WorkerW")
            is_fullscreen = (not is_desktop
                             and rect[0] <= mon_rect[0] and rect[1] <= mon_rect[1]
                             and rect[2] >= mon_rect[2] and rect[3] >= mon_rect[3])
        except Exception:
            is_fullscreen = False

        return process_name, window_title, is_fullscreen

    def _run(self):
        self.last_check_time = time.time()

        while self.running:
            try:
                self.interval = max(1, int(config.get("refresh_interval", 5)))
            except (TypeError, ValueError):
                self.interval = 5
            time.sleep(self.interval)

            now = time.time()
            elapsed = int(round(now - self.last_check_time))
            self.last_check_time = now

            # After a sleep / hibernation (or a clock change) the loop wakes up with a
            # huge `elapsed`: that time was not spent in front of the screen.
            if elapsed > self.interval * 3 + 5:
                elapsed = self.interval
            if elapsed <= 0:
                continue

            try:
                self._tick(now, elapsed)
            except Exception as e:
                # Never let a transient error kill the tracking thread.
                print(f"Tracker error: {e}")

            if now - self.last_purge_time > PURGE_EVERY:
                self.last_purge_time = now
                try:
                    db.purge_old_data(config.get("retention_days", 365))
                except Exception as e:
                    print(f"Purge error: {e}")

    def _tick(self, now, elapsed):
        app_name, window_title, is_fullscreen = self._get_active_window_info()

        status = 'active'
        if config.get("detect_fullscreen", True) and is_fullscreen:
            status = 'fullscreen'

        if app_name.lower() in LOCK_SCREEN_PROCESSES:
            status = 'idle'
        elif config.get("detect_idle", True):
            # Idle overrides fullscreen
            idle_time = self._get_idle_time()
            max_idle = config.get("idle_timeout", 300)
            if idle_time > max_idle:
                status = 'idle'

        db.insert_log(app_name, window_title, status, elapsed, end_ts=int(now))


tracker = Tracker()
