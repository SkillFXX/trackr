import sys
import os
import webview
import threading
import win32event
import win32api
import winerror
import time
import ctypes

from .api import Api, set_window
from .tracker import tracker
from .tray import TrayIcon
from .config import config, APP_DATA_DIR

MUTEX_NAME = "Trackr_SingleInstance_Mutex"
# Set by a second instance to ask the running one to show its window
SHOW_EVENT_NAME = "Trackr_ShowWindow_Event"
EVENT_MODIFY_STATE = 0x0002
user32 = ctypes.windll.user32

def bring_to_foreground(hwnd):
    """Force brings the window to the foreground and un-minimizes if needed."""
    if not hwnd or not user32.IsWindow(hwnd):
        return
    try:
        # 1. Un-minimize if iconic / minimized, otherwise show normal
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        else:
            user32.ShowWindow(hwnd, 5)  # SW_SHOW

        # 2. Bypass Windows foreground lock using AttachThreadInput
        fore_hwnd = user32.GetForegroundWindow()
        fore_tid = user32.GetWindowThreadProcessId(fore_hwnd, None) if fore_hwnd else 0
        cur_tid = win32api.GetCurrentThreadId()

        if fore_tid and fore_tid != cur_tid:
            user32.AttachThreadInput(fore_tid, cur_tid, True)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(fore_tid, cur_tid, False)
        else:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)

        # 3. Z-order toggle (HWND_TOPMOST -> HWND_NOTOPMOST) to guarantee placement above other windows
        SWP_FLAGS = 1 | 2 | 0x40  # SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
        user32.SetWindowPos(hwnd, -1, 0, 0, 0, 0, SWP_FLAGS)  # HWND_TOPMOST
        user32.SetWindowPos(hwnd, -2, 0, 0, 0, 0, SWP_FLAGS)  # HWND_NOTOPMOST
        user32.SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"Error in bring_to_foreground: {e}")

def check_single_instance():
    mutex = win32event.CreateMutex(None, 1, MUTEX_NAME)
    if win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS:
        # App is already running
        return False, None
    return True, mutex

def signal_running_instance():
    """Ask the already running instance to show its window."""
    try:
        event = win32event.OpenEvent(EVENT_MODIFY_STATE, False, SHOW_EVENT_NAME)
        win32event.SetEvent(event)
        # Allow the running instance (a different process) to take the foreground
        user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        return True
    except Exception as e:
        print(f"Failed to signal running instance: {e}")
    try:
        hwnd = user32.FindWindowW(None, "Trackr")
        if hwnd and user32.IsWindow(hwnd):
            bring_to_foreground(hwnd)
            return True
    except Exception as e:
        print(f"Failed to focus existing window: {e}")
    return False


def main():
    # 1. Single instance check
    is_first_instance, mutex = check_single_instance()
    if not is_first_instance:
        print("Application is already running.")
        signal_running_instance()
        sys.exit(0)

    show_event = win32event.CreateEvent(None, False, False, SHOW_EVENT_NAME)

    # Keep the "start with Windows" registry entry in sync with the settings
    config.sync_startup()

    # 2. Start Tracker (also purges data older than the retention setting)
    tracker.start()

    # 3. Webview logic
    api = Api()
    
    # Path to frontend
    from .utils import get_base_path
    base_dir = get_base_path()
    index_path = os.path.join(base_dir, 'frontend', 'index.html')
    
    # To handle 'hidden' mode when starting with Windows
    hidden = "--hidden" in sys.argv
    
    window = webview.create_window('Trackr', url=index_path, js_api=api, width=1280, height=820,
                                   min_size=(960, 640), hidden=hidden)
    set_window(window)
    
    _last_show_time = 0
    _show_lock = threading.Lock()

    def on_show_window(*args, **kwargs):
        nonlocal _last_show_time
        with _show_lock:
            now = time.time()
            # Debounce rapid clicks (e.g. double-click in tray) within 400ms
            if now - _last_show_time < 0.4:
                return
            _last_show_time = now

        if window:
            try:
                # Restore window state first so it doesn't show as minimized
                window.restore()
                window.show()
            except Exception as e:
                print(f"Error restoring/showing pywebview window: {e}")

            try:
                hwnd = None
                if hasattr(window, 'native') and window.native:
                    hwnd = int(window.native.Handle.ToInt64())
                if not hwnd or not user32.IsWindow(hwnd):
                    hwnd = user32.FindWindowW(None, "Trackr")
                if hwnd and user32.IsWindow(hwnd):
                    bring_to_foreground(hwnd)
            except Exception as e:
                print(f"Error bringing window to foreground: {e}")

            # The page may have been loaded hours ago (hidden start with Windows):
            # reload the data every time the window is shown.
            try:
                window.evaluate_js("window.app && window.app.onWindowShown && window.app.onWindowShown()")
            except Exception as e:
                print(f"Error refreshing data: {e}")

    def wait_for_show_requests():
        while True:
            win32event.WaitForSingleObject(show_event, win32event.INFINITE)
            on_show_window()

    threading.Thread(target=wait_for_show_requests, daemon=True).start()

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
    
    # 5. Start Webview event loop (blocks until window is closed or app exits)
    webview.start(debug=False)

if __name__ == '__main__':
    main()
