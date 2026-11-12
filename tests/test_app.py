"""The native app layer. Opens a hidden window, so it runs only with CUI_WINDOW_TESTS=1."""

import os

import pytest

import cui

pytestmark = pytest.mark.skipif(
    os.environ.get("CUI_WINDOW_TESTS") != "1",
    reason="opens a window; set CUI_WINDOW_TESTS=1",
)


def test_frames_paint_and_screenshot() -> None:
    painted: list[cui.Rect] = []
    with cui.App("test", 320, 200, hidden=True) as app:
        assert app.backend() in ("cocoa", "win32", "x11", "sdl2", "glfw")
        n = 0
        for ui in app.frames():
            with ui.column(pad=16):
                ui.button("Hello")
                ui.canvas(
                    "c", 40, 40, painted.append
                )  # runs inside cui_app_frame, without the GIL held
            n += 1
            if n == 3:
                app.quit()
        assert n == 3
        assert len(painted) >= 2
        w, h, pixels = app.screenshot()
        assert w >= 320 and h >= 200  # pixels, so larger on a HiDPI display
        assert len(pixels) == w * h * 4
        with pytest.raises(RuntimeError):
            app.ui.begin_frame()  # an App owns its frames
    with pytest.raises(RuntimeError, match="closed"):
        app.frame()


def test_paint_error_from_app_frame() -> None:
    def paint(r: cui.Rect) -> None:
        raise LookupError("in paint")

    with cui.App("test", 200, 100, hidden=True) as app:
        assert app.frame()
        app.ui.canvas("c", 10, 10, paint)
        with pytest.raises(LookupError):
            app.frame()
