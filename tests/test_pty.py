"""cui.Pty and ui.pty: a child on a pty, shown in a headless context."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

import pytest

import cui

from .conftest import key, run

needs_pty = pytest.mark.skipif(not cui.PTY_AVAILABLE, reason="built without CUI_PY_PTY")
PASTE = cui.MOD_SUPER if sys.platform == "darwin" else cui.MOD_CTRL | cui.MOD_SHIFT


def until(
    ctx: cui.Context, p: cui.Pty, done: Callable[[], bool], timeout: float = 5.0
) -> None:
    """Runs frames that show p until done() holds."""
    end = time.monotonic() + timeout
    while not done():
        if time.monotonic() > end:
            pytest.fail(f"timed out; screen: {p.screen()!r}")
        run(ctx, lambda ui: ui.pty("t", p))
        time.sleep(0.005)


@pytest.mark.skipif(cui.PTY_AVAILABLE, reason="built with CUI_PY_PTY")
def test_unavailable_raises() -> None:
    with pytest.raises(RuntimeError, match="CUI_PY_PTY"):
        cui.Pty()


@needs_pty
def test_output_and_exit_code(ctx: cui.Context) -> None:
    with cui.Pty(["/bin/sh", "-c", "printf 'hello pty\\n'; exit 3"]) as p:
        assert p.exit_code is None or p.exited
        until(ctx, p, lambda: p.exited)
        assert p.screen() == "hello pty"
        assert p.exit_code == 3


@needs_pty
def test_cwd_and_title(ctx: cui.Context, tmp_path: Path) -> None:
    script = 'printf \'\\033]0;my title\\007\'; [ "$(pwd -P)" = "$1" ] && echo same'
    with cui.Pty(
        ["/bin/sh", "-c", script, "sh", str(tmp_path.resolve())], cwd=tmp_path
    ) as p:
        until(ctx, p, lambda: p.exited)
        assert p.title == "my title"
        assert p.screen() == "same"


@needs_pty
def test_write_typing_and_enter(ctx: cui.Context) -> None:
    with cui.Pty(["cat"]) as p:
        run(ctx, lambda ui: ui.pty("t", p))  # first frame takes focus
        p.write("one\n")
        until(ctx, p, lambda: p.screen().count("one") == 2)  # the tty echo, then cat
        ctx.input_text("two")
        run(ctx, lambda ui: ui.pty("t", p))  # in one frame, keys go before text
        key(ctx, lambda ui: ui.pty("t", p), cui.KEY_ENTER)
        until(ctx, p, lambda: p.screen().count("two") == 2)


@needs_pty
def test_paste_sends_safe_text_and_holds_unsafe(ctx: cui.Context) -> None:
    build: Callable[[cui.Context], object] = lambda ui: ui.pty("t", p)
    with cui.Pty(["cat"]) as p:
        run(ctx, build)
        ctx.clipboard = "pasted"
        key(ctx, build, cui.KEY_V, PASTE)
        until(ctx, p, lambda: "pasted" in p.screen())
        ctx.clipboard = "echo unsafe\n"  # a line break runs a command: asks first
        key(ctx, build, cui.KEY_V, PASTE)
        for _ in range(20):
            run(ctx, build)
        assert "unsafe" not in p.screen()


@needs_pty
def test_copy_selection_is_empty_without_drag(ctx: cui.Context) -> None:
    with cui.Pty(["/bin/sh", "-c", "echo x"]) as p:
        until(ctx, p, lambda: p.exited)
        assert p.screen(selection=True) == ""


@needs_pty
def test_close_during_frame_waits_for_frame_end(ctx: cui.Context) -> None:
    p = cui.Pty(["cat"])
    with ctx.frame():
        ctx.pty("t", p)
        p.close()
        with pytest.raises(RuntimeError, match="closed"):
            p.write("x")
    ctx.render()
    with pytest.raises(RuntimeError, match="closed"):
        p.screen()
    p.close()  # twice is fine


@needs_pty
def test_other_thread_raises() -> None:
    errors: list[BaseException] = []
    with cui.Pty(["cat"]) as p:

        def use() -> None:
            try:
                p.write("x")
            except RuntimeError as e:
                errors.append(e)

        t = threading.Thread(target=use)
        t.start()
        t.join()
    assert len(errors) == 1 and "thread" in str(errors[0])


@needs_pty
def test_view_needs_a_frame(ctx: cui.Context) -> None:
    with cui.Pty(["cat"]) as p, pytest.raises(RuntimeError, match="inside a frame"):
        ctx.pty("t", p)


@needs_pty
def test_bad_arguments() -> None:
    with pytest.raises(ValueError, match="empty"):
        cui.Pty([])
    with pytest.raises(TypeError, match="sequence"):
        cui.Pty("ls")  # a str is a Sequence[str], so only the runtime check catches it
    with pytest.raises(ValueError, match="NUL"):
        cui.Pty(["a\0b"])
    with pytest.raises(ValueError, match="font_size"):
        cui.Pty(["cat"], font_size=2)


@needs_pty
def test_missing_program_exits_127(ctx: cui.Context) -> None:
    with cui.Pty(["/nonexistent/program"]) as p:
        until(ctx, p, lambda: p.exited)
        assert p.exit_code == 127
