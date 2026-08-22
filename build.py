import PyInstaller.__main__
import os
import shutil

if __name__ == '__main__':
    print("Building Trackr...")
    
    # Create empty icon just to avoid pyinstaller failure if not present
    assets_dir = os.path.join('frontend', 'assets')
    os.makedirs(assets_dir, exist_ok=True)
    icon_path = os.path.join(assets_dir, 'icon.ico')
    if not os.path.exists(icon_path):
        from PIL import Image
        img = Image.new('RGB', (64, 64), color=(59, 130, 246))
        img.save(icon_path)

    PyInstaller.__main__.run([
        'run.py',
        '--name=Trackr',
        '--onefile',
        '--windowed',
        '--noconsole',
        '--icon=frontend/assets/icon.ico',
        '--add-data=frontend;frontend',
        '--clean',
        '-y'
    ])
    
    print("Build complete. Check the 'dist' folder.")
