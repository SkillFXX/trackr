import sys
import os
import webview
import threading
import win32event
import win32api
import winerror
import time

from .api import Api
from .tracker import tracker
from .tray import TrayIcon
from .config import config, APP_DATA_DIR

MUTEX_NAME = "Trackr_SingleInstance_Mutex"

def check_single_instance():
    mutex = win32event.CreateMutex(None, 1, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        # App is already running
        return False, None
    return True, mutex

def main():
    # 1. Single instance check
    is_first_instance, mutex = check_single_instance()
    if not is_first_instance:
        print("Application is already running.")
        sys.exit(0)

    # 2. Start Tracker
    tracker.start()

    # 3. Webview logic
    api = Api()
    
    # Path to frontend
    from .utils import get_base_path
    base_dir = get_base_path()
    index_path = os.path.join(base_dir, 'frontend', 'index.html')
    
    # To handle 'hidden' mode when starting with Windows
    hidden = "--hidden" in sys.argv
    
    window = webview.create_window('Trackr', url=index_path, js_api=api, width=1024, height=768, hidden=hidden)
    
    def on_show_window():
        if window:
            window.show()
            window.restore()

    def on_closing():
        window.hide()
        return False # Prevents the window from destroying the webview loop

    window.events.closing += on_closing

    def on_quit():
        tracker.stop()
        if window:
            window.destroy()
        os._exit(0)

    # 4. System Tray
    tray = TrayIcon(on_show_window, on_quit)
    tray.run()
    
    # Check retention
    retention_days = config.get("retention_days", 30)
    from .db import db
    db.purge_old_data(retention_days)

    # 5. Start Webview event loop (blocks until window is closed or app exits)
    webview.start(debug=False)

if __name__ == '__main__':
    main()
