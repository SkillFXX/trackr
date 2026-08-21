import pystray
from PIL import Image, ImageDraw
import threading
import sys
import os

class TrayIcon:
    def __init__(self, on_show_window, on_quit):
        self.on_show_window = on_show_window
        self.on_quit = on_quit
        self.icon = None

    def _create_image(self):
        # Generate a simple icon if we don't have an asset
        # Try to load from assets first
        from .utils import get_base_path
        asset_path = os.path.join(get_base_path(), 'frontend', 'assets', 'icon.ico')
        if os.path.exists(asset_path):
            return Image.open(asset_path)
            
        # Fallback generated icon
        image = Image.new('RGB', (64, 64), color=(30, 41, 59))
        dc = ImageDraw.Draw(image)
        dc.rectangle([16, 16, 48, 48], fill=(59, 130, 246))
        return image

    def run(self):
        menu = pystray.Menu(
            pystray.MenuItem("Afficher Trackr", self.on_show_window, default=True),
            pystray.MenuItem("Quitter", self._quit)
        )
        self.icon = pystray.Icon("Trackr", self._create_image(), "Trackr", menu)
        
        # Run in a separate thread so it doesn't block the main thread (webview)
        self.thread = threading.Thread(target=self.icon.run, daemon=True)
        self.thread.start()

    def _quit(self, icon, item):
        self.icon.stop()
        self.on_quit()
