import os
import json
import winreg
import sys

# Define AppData path
APP_DATA_DIR = os.path.join(os.getenv('APPDATA'), 'Trackr')
CONFIG_FILE = os.path.join(APP_DATA_DIR, 'config.json')

DEFAULT_CONFIG = {
    "language": "fr",
    "startup": True,
    "idle_timeout": 300, # 5 minutes
    "retention_days": 30,
    "refresh_interval": 5,
    "detect_idle": True,
    "detect_fullscreen": True,
    "categories": {
        "Development": ["code", "devenv", "idea", "pycharm", "webstorm", "git", "cmd", "powershell", "WindowsTerminal"],
        "Web": ["chrome", "firefox", "msedge", "brave", "opera"],
        "Communication": ["discord", "slack", "teams", "skype", "telegram", "whatsapp"],
        "Jeux": ["steam", "epicgameslauncher", "riotclient", "val", "csgo"],
        "Productivité": ["winword", "excel", "powerpnt", "notion", "obsidian"]
    }
}

class ConfigManager:
    def __init__(self):
        self.config = DEFAULT_CONFIG.copy()
        self._ensure_app_data_dir()
        self.load()

    def _ensure_app_data_dir(self):
        if not os.path.exists(APP_DATA_DIR):
            os.makedirs(APP_DATA_DIR)

    def load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                    user_config = json.load(f)
                    self.config.update(user_config)
            except Exception as e:
                print(f"Error loading config: {e}")
        else:
            self.save()

    def save(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key, default=None):
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value
        self.save()
        if key == "startup":
            self.toggle_startup(value)

    def get_category_for_app(self, app_name):
        app_name_lower = app_name.lower().replace('.exe', '')
        for category, apps in self.config.get("categories", {}).items():
            if any(app.lower() in app_name_lower for app in apps):
                return category
        return "Non catégorisé"

    def toggle_startup(self, enable):
        """Enable or disable startup with Windows using the Registry."""
        if sys.platform != 'win32':
            return
            
        key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
        app_name = "Trackr"
        
        # Path to the current executable (or script if running from python)
        if getattr(sys, 'frozen', False):
            app_path = sys.executable
        else:
            # If running as a script, we might not want to add python to startup,
            # but for testing we can. Usually startup is only for the compiled exe.
            app_path = f'"{sys.executable}" "{os.path.abspath(sys.argv[0])}"'
            
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_ALL_ACCESS)
            if enable:
                # Wrap app_path in quotes in case it contains spaces
                if getattr(sys, 'frozen', False):
                    cmd = f'"{app_path}" --hidden'
                else:
                    cmd = f'{app_path} --hidden'
                winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, app_name)
                except FileNotFoundError:
                    pass
            winreg.CloseKey(key)
        except Exception as e:
            print(f"Error toggling startup: {e}")

config = ConfigManager()
