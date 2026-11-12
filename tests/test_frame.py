"""Frame lifecycle and the guards that turn misuse into exceptions."""

import pytest

import cui

from .conftest import run


def test_component_outside_frame(ctx: cui.Context) -> None:
    with pytest.raises(RuntimeError, match="inside a frame"):
        ctx.button("x")


def test_begin_twice(ctx: cui.Context) -> None:
    ctx.begin_frame()
    with pytest.raises(RuntimeError):
        ctx.begin_frame()
    ctx.end_frame()


def test_end_without_begin(ctx: cui.Context) -> None:
    with pytest.raises(RuntimeError):
        ctx.end_frame()


def test_end_frame_with_open_scope(ctx: cui.Context) -> None:
    ctx.begin_frame()
    s = ctx.row()
    s.__enter__()
    with pytest.raises(RuntimeError, match="still open"):
        ctx.end_frame()
    s.__exit__(None, None, None)
    ctx.end_frame()


def test_input_outside_frame(ctx: cui.Context) -> None:
    ctx.input_mouse_move(10, 10)  # input is collected for the next frame
    ctx.set_theme(cui.THEME_DARK)
    assert ctx.get_theme_mode() == cui.THEME_DARK


def test_closed_context(ctx: cui.Context) -> None:
    ctx.close()
    with pytest.raises(RuntimeError, match="closed"):
        ctx.begin_frame()
    with pytest.raises(RuntimeError, match="closed"):
        ctx.input_mouse_move(1, 1)


def test_draw_outside_paint(ctx: cui.Context) -> None:
    with ctx.frame(), pytest.raises(RuntimeError, match="paint callback"):
        ctx.draw_circle((10, 10), 5, cui.rgb(0xFF0000))


def test_exception_in_frame_ends_it(ctx: cui.Context) -> None:
    with pytest.raises(ZeroDivisionError), ctx.frame(), ctx.column():
        ctx.text("x")
        raise ZeroDivisionError
    assert not ctx.in_frame
    run(ctx, lambda ui: ui.text("next frame works"))


def test_render(ctx: cui.Context) -> None:
    with pytest.raises(RuntimeError):
        ctx.render()
    run(ctx, lambda ui: ui.button("Hello"))
    pixels = ctx.render()
    assert ctx.render_size() == (800, 600)
    assert len(pixels) == 800 * 600 * 4
    assert len({pixels[i : i + 4] for i in range(0, len(pixels), 4 * 97)}) > 2
    vertices, indices, commands = ctx.draw_counts()
    assert vertices > 0 and indices > 0 and commands > 0


def test_render_scale() -> None:
    with cui.Context(100, 50, 2.0) as c:
        run(c, lambda ui: ui.text("x"))
        assert c.render_size() == (200, 100)


def test_save_png(ctx: cui.Context, tmp_path) -> None:  # type: ignore[no-untyped-def]
    run(ctx, lambda ui: ui.text("png"))
    p = tmp_path / "f.png"
    ctx.save_png(p)
    assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_write_png_checks_size(tmp_path) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(ValueError):
        cui.write_png(tmp_path / "x.png", b"\0" * 15, 2, 2)


def test_frames_release_strings(ctx: cui.Context) -> None:
    # Strings live until the frame ends; a long run must not accumulate them.
    import gc

    def build(ui: cui.Context) -> None:
        for i in range(50):
            ui.text(f"line {i}")

    run(ctx, build, 5)
    gc.collect()
    before = len(gc.get_objects())
    run(ctx, build, 200)
    gc.collect()
    assert len(gc.get_objects()) - before < 100
