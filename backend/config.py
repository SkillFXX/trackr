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
        self.config[key] = value
        self.save()
        if key == "startup":
            self.toggle_startup(value)

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
                    import re
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
