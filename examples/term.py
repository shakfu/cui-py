"""A terminal in a window: the Python port of cui-repl's main.c. Needs CUI_PY_PTY=ON.

    python examples/term.py [COMMAND [ARG...]]

Without COMMAND it runs $SHELL. It exits with the child's exit code.
"""

import os
import sys

import cui

# Faces for what Geist Mono lacks: symbols, CJK. CUI takes 4 fallbacks per face.
FALLBACKS = (
    [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Apple Symbols.ttf",
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    ]
    if sys.platform == "darwin"
    else [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/TTF/DejaVuSansMono.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
)


def load_fonts(ui: cui.Context) -> None:
    added = 0
    for path in FALLBACKS:
        if added < 4 and os.access(path, os.R_OK):
            f = ui.font_load_file(path)
            if f >= 0:
                ui.font_add_fallback(cui.FONT_MONO, f)
                added += 1


class Term:
    def __init__(self, argv: list[str] | None = None) -> None:
        self.pty = cui.Pty(argv or None)
        self.title = ""

    def build(self, ui: cui.Context) -> None:
        ui.pty("terminal", self.pty)


def main() -> int:
    term = Term(sys.argv[1:])
    with cui.App("term", 900, 560) as app, term.pty:
        load_fonts(app.ui)
        for ui in app.frames():
            term.build(ui)
            if term.pty.title != term.title:
                term.title = term.pty.title
                app.set_title(term.title or "term")
            if term.pty.exited:
                break
        code = term.pty.exit_code
    return 0 if code is None else code


if __name__ == "__main__":
    sys.exit(main())
