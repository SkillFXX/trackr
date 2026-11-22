import os
import re
import json
import sys

IS_WINDOWS = sys.platform == 'win32'
if IS_WINDOWS:
    import winreg

# Define AppData path (TRACKR_DATA_DIR allows using a separate folder for testing)
APP_DATA_DIR = os.getenv('TRACKR_DATA_DIR') or os.path.join(
    os.getenv('APPDATA') or os.path.expanduser('~'), 'Trackr')
CONFIG_FILE = os.path.join(APP_DATA_DIR, 'config.json')

DEFAULT_CONFIG = {
    "language": "fr",
    "startup": True,
    "idle_timeout": 300, # 5 minutes
    "retention_days": 365,
    "refresh_interval": 5,
    "detect_idle": True,
    "detect_fullscreen": True,
    "categories": {
        "Développement": [
            "code", "devenv", "idea", "pycharm", "webstorm", "clion", "rider", "datagrip",
            "visualstudio", "sublime_text", "notepad++", "cursor", "antigravity", "git",
            "githubdesktop", "cmd", "powershell", "windowsterminal", "bash", "wsl", "docker",
            "postman", "dbeaver", "pgadmin", "insomnia", "figma", "unity", "unreal"
        ],
        "Navigation Web": [
            "chrome", "firefox", "msedge", "brave", "opera", "vivaldi", "arc", "safari", "tor"
        ],
        "Jeux": [
            "steam", "steamwebhelper", "epicgameslauncher", "riotclient", "riotclientux",
            "val", "csgo", "cs2", "cod", "cod23-cod", "minecraft", "roblox", "overwatch",
            "apex", "genshin", "littlebigworkshop", "how to fish", "battle.net", "gta5",
            "rdr2", "cyberpunk2077", "ea", "origin", "ubisoftconnect", "galaxyclient"
        ],
        "Communication": [
            "discord", "slack", "teams", "skype", "telegram", "whatsapp", "signal",
            "thunderbird", "outlook", "messenger", "zoom"
        ],
        "Productivité": [
            "winword", "excel", "powerpnt", "notion", "obsidian", "acrobat", "acrord32",
            "reader", "onenote", "evernote", "todoist", "libreoffice", "calc", "writer"
        ],
        "Multimédia & Musique": [
            "spotify", "vlc", "netflix", "itunes", "deezer", "foobar2000", "youtube",
            "potplayer", "mediaplayer", "audacity"
        ],
        "Création & Design": [
            "photoshop", "illustrator", "premiere", "afterfx", "lightroom", "indesign",
            "blender", "canva", "gimp", "inkscape", "cinema4d", "davinci"
        ],
        "Système & Utilitaires": [
            "explorer", "taskmgr", "mmc", "regedit", "systemsettings", "control",
            "7zfm", "winrar", "notepad", "calculator"
        ]
    },
    "app_overrides": {}
}

# Mapping of categories to productivity types
PRODUCTIVITY_MAP = {
    "Développement": "productive",
    "Productivité": "productive",
    "Création & Design": "productive",
    "Development": "productive",
    "Jeux": "entertainment",
    "Multimédia & Musique": "entertainment",
    "Communication": "communication",
    "Navigation Web": "neutral",
    "Web": "neutral",
    "Système & Utilitaires": "neutral",
    "Non catégorisé": "neutral",
    "Inconnu": "neutral"
}

class ConfigManager:
    def __init__(self):
        self.config = json.loads(json.dumps(DEFAULT_CONFIG))
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
                    
                # Merge base settings
                for k, v in user_config.items():
                    if k != "categories":
                        self.config[k] = v
                        
                # Merge categories intelligently (do not wipe default categories)
                if "categories" in user_config and isinstance(user_config["categories"], dict):
                    # Handle migration from older english names if needed
                    cats = user_config["categories"]
                    if "Development" in cats and "Développement" not in cats:
                        cats["Développement"] = cats.pop("Development")
                    if "Web" in cats and "Navigation Web" not in cats:
                        cats["Navigation Web"] = cats.pop("Web")
                        
                    for cat, apps in DEFAULT_CONFIG["categories"].items():
                        if cat not in cats:
                            cats[cat] = apps
                        else:
                            # Add missing default apps without duplicates
                            existing_lower = [a.lower() for a in cats[cat]]
                            for app in apps:
                                if app.lower() not in existing_lower:
                                    cats[cat].append(app)
                    self.config["categories"] = cats
                else:
                    self.config["categories"] = DEFAULT_CONFIG["categories"].copy()
                    
                if "app_overrides" not in self.config:
                    self.config["app_overrides"] = {}
                self.save()
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
        self.set_many({key: value})

    def set_many(self, values):
        startup_changed = "startup" in values
        for k, v in values.items():
            self.config[k] = v
        self.save()
        if startup_changed:
            self.toggle_startup(bool(values["startup"]), explicit=True)

    def get_category_for_app(self, app_name):
        if not app_name or app_name.lower() == "unknown":
            return "Inconnu"
            
        app_name_lower = app_name.lower().replace('.exe', '').strip()
        
        # 1. Check user overrides first
        overrides = self.config.get("app_overrides", {})
        for ov_key, ov_cat in overrides.items():
            if ov_key.lower().replace('.exe', '').strip() == app_name_lower:
                return ov_cat
                
        # 2. Match with categories:
        # First check exact match
        for category, apps in self.config.get("categories", {}).items():
            for app in apps:
                app_clean = app.lower().replace('.exe', '').strip()
                if app_name_lower == app_clean:
                    return category

        # Second check substring / boundary match (avoiding short substrings matching inside longer words)
        for category, apps in self.config.get("categories", {}).items():
            for app in apps:
                app_clean = app.lower().replace('.exe', '').strip()
                if len(app_clean) >= 4 and app_clean in app_name_lower:
                    # e.g. "epicgameslauncher", "antigravity", "spotify", "discord", "powershell"
                    return category
                elif len(app_clean) < 4:
                    # For short tokens (e.g. 'val', 'git', 'cmd'), ensure word boundary or exact match
                    if re.search(rf"(^|[^a-z0-9]){re.escape(app_clean)}([^a-z0-9]|$)", app_name_lower):
                        return category
                
        return "Non catégorisé"

    def set_app_category(self, app_name, category):
        if not app_name:
            return
        if "app_overrides" not in self.config:
            self.config["app_overrides"] = {}
        clean_name = app_name.strip()
        self.config["app_overrides"][clean_name] = category
        self.save()

    def get_productivity_type(self, category):
        return PRODUCTIVITY_MAP.get(category, "neutral")

    # ------------------------------------------------------------------ startup

    def get_startup_command(self):
        """Command line written in the registry to launch Trackr at logon."""
        if getattr(sys, 'frozen', False):
            return f'"{sys.executable}" --hidden'
        # Running from sources: use pythonw.exe so that no console window pops up.
        python = sys.executable
        pythonw = os.path.join(os.path.dirname(python), 'pythonw.exe')
        if os.path.exists(pythonw):
            python = pythonw
        from .utils import get_base_path
        script = os.path.join(get_base_path(), 'run.py')
        return f'"{python}" "{script}" --hidden'

    def toggle_startup(self, enable, explicit=False):
        """Enable or disable startup with Windows (HKCU Run key).

        When the user explicitly turns the option on, the "disabled" flag that
        Windows keeps when an app is turned off in the Task Manager / Settings
        startup page is cleared too, otherwise the Run entry would be ignored.
        """
        if not IS_WINDOWS:
            return False
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0,
                                winreg.KEY_SET_VALUE | winreg.KEY_QUERY_VALUE) as key:
                if enable:
                    winreg.SetValueEx(key, STARTUP_VALUE_NAME, 0, winreg.REG_SZ, self.get_startup_command())
                else:
                    try:
                        winreg.DeleteValue(key, STARTUP_VALUE_NAME)
                    except FileNotFoundError:
                        pass
        except OSError as e:
            print(f"Error toggling startup: {e}")
            return False

        if enable and explicit:
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, STARTUP_VALUE_NAME)
            except OSError:
                pass
        return True

    def get_startup_status(self):
        """Real state of the startup entry, as seen by Windows."""
        status = {"supported": IS_WINDOWS, "registered": False, "up_to_date": False,
                  "disabled_by_windows": False, "command": None}
        if not IS_WINDOWS:
            return status
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
                value, _ = winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
                status["registered"] = True
                status["command"] = value
                status["up_to_date"] = os.path.normcase(value) == os.path.normcase(self.get_startup_command())
        except OSError:
            pass
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, APPROVED_KEY, 0, winreg.KEY_QUERY_VALUE) as key:
                data, _ = winreg.QueryValueEx(key, STARTUP_VALUE_NAME)
                # First byte: 0x02 / 0x06 = enabled, 0x03 / 0x07 = disabled by the user
                if data and (data[0] & 0x01):
                    status["disabled_by_windows"] = True
        except OSError:
            pass
        return status

    def sync_startup(self):
        """Make the registry match the saved setting (called at every launch).

        Only done for the packaged executable: this also fixes the entry when
        Trackr.exe has been moved, and registers it on the very first launch
        (the option is enabled by default but used to be written only when the
        settings were saved).
        """
        if not IS_WINDOWS or not getattr(sys, 'frozen', False):
            return
        self.toggle_startup(bool(self.config.get("startup", True)))


RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
STARTUP_VALUE_NAME = "Trackr"

config = ConfigManager()
