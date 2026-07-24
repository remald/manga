"""Registers the bundled fonts (manga_ui/fonts) with Qt so they're available
for rendering regardless of what the user has installed. Needs a running
QGuiApplication; call once at startup (GUI and CLI both do)."""
from pathlib import Path

from PySide6.QtGui import QFontDatabase

FONTS_DIR = Path(__file__).parent / "fonts"
_loaded = False


def load_bundled_fonts():
    global _loaded
    if _loaded:
        return
    for ttf in sorted(FONTS_DIR.glob("*.ttf")):
        QFontDatabase.addApplicationFont(str(ttf))
    _loaded = True
