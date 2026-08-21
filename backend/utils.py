import sys
import os

def get_base_path():
    """Get absolute path to resource, works for dev and for PyInstaller"""
    if getattr(sys, 'frozen', False):
        # Running in PyInstaller bundle
        return sys._MEIPASS
    else:
        # Running normally
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
