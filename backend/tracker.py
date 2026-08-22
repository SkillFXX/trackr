import time
import threading
import win32gui
import win32process
import win32api
import psutil
from .db import db
from .config import config

class Tracker:
    def __init__(self):
        self.running = False
        self.thread = None
        self.interval = 5  # Check every 5 seconds
        self.last_check_time = time.time()
        self.current_app = None
        self.current_title = None
        self.app_start_time = time.time()
        self.is_idle = False
        
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
        return (current_tick - last_input_info) / 1000.0

    def _get_active_window_info(self):
        """Returns (process_name, window_title, is_fullscreen)."""
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return "Unknown", "Unknown", False
            
        # Get window title
        try:
            window_title = win32gui.GetWindowText(hwnd)
        except:
            window_title = "Unknown"
            
        # Get process name
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            process = psutil.Process(pid)
            process_name = process.name()
        except:
            process_name = "Unknown"
            
        # Check fullscreen (approximate by comparing to screen size)
        try:
            rect = win32gui.GetWindowRect(hwnd)
            w = rect[2] - rect[0]
            h = rect[3] - rect[1]
            screen_w = win32api.GetSystemMetrics(0)
            screen_h = win32api.GetSystemMetrics(1)
            is_fullscreen = (w >= screen_w and h >= screen_h)
        except:
            is_fullscreen = False
            
        return process_name, window_title, is_fullscreen

    def _run(self):
        self.last_check_time = time.time()
        
        while self.running:
            # Update interval dynamically
            self.interval = config.get("refresh_interval", 5)
            time.sleep(self.interval)
            
            now = time.time()
            elapsed = int(now - self.last_check_time)
            self.last_check_time = now
            
            app_name, window_title, is_fullscreen = self._get_active_window_info()
            
            status = 'active'
            
            # Fullscreen detection toggle
            if config.get("detect_fullscreen", True) and is_fullscreen:
                status = 'fullscreen'
                
            # Idle detection toggle (Overrides fullscreen if idle)
            if config.get("detect_idle", True):
                idle_time = self._get_idle_time()
                max_idle = config.get("idle_timeout", 300)
                if idle_time > max_idle:
                    status = 'idle'
                
            # Log the time
            db.insert_log(app_name, window_title, status, elapsed)
            
            # Daily cleanup (simple approach: check randomly or just on start)
            # We can do it in api.py or here periodically. 
            # Doing it here every ~hour would be fine, but for simplicity we rely on startup purge.

tracker = Tracker()
