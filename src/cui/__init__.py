"""Python bindings for CUI, an immediate-mode UI library in C.

import cui

app = cui.App("Hello", 420, 300)
for ui in app.frames():
    with ui.column(pad=32, gap=16):
        ui.heading("Hello, CUI", 2)
        if ui.button("Click me", variant=cui.BUTTON_PRIMARY):
            print("clicked")
"""

from cui._core import *
from cui._core import VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH

__version__ = "0.1.0"
CUI_VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"
