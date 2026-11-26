"""Canvas paint callbacks: drawing, and errors raised inside them."""

from typing import Any

import pytest

import cui

from .conftest import run


def test_paint_runs_with_rect(ctx: cui.Context) -> None:
    rects: list[cui.Rect] = []

    def paint(r: cui.Rect) -> None:
        rects.append(r)
        ctx.draw_rect(r, 4, cui.rgb(0x3366FF))
        ctx.draw_circle((r.x + 10, r.y + 10), 5, cui.COLOR_ACCENT)
        ctx.draw_polyline(
            [(r.x, r.y), (r.x + 50, r.y + 20), (r.x + 90, r.y)], 2, cui.rgb(0), False
        )
        ctx.draw_text(
            cui.FONT_BODY, 14, (r.x, r.y + 30), cui.COLOR_FOREGROUND, "painted"
        )

    out: list[Any] = []
    run(ctx, lambda ui: out.append(ui.canvas("c", 200, 100, paint)), 2)
    assert len(rects) == 2
    assert rects[-1].w == 200 and rects[-1].h == 100
    assert isinstance(out[-1], cui.CanvasResult)


def test_paint_error_propagates(ctx: cui.Context) -> None:
    def paint(r: cui.Rect) -> None:
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        run(ctx, lambda ui: ui.canvas("c", 10, 10, paint))
    run(ctx, lambda ui: ui.text("recovered"))


def test_components_inside_paint_raise(ctx: cui.Context) -> None:
    def paint(r: cui.Rect) -> None:
        ctx.button("no")

    with pytest.raises(RuntimeError, match="paint callback"):
        run(ctx, lambda ui: ui.canvas("c", 10, 10, paint))


def test_paint_must_be_callable(ctx: cui.Context) -> None:
    with ctx.frame(), pytest.raises(TypeError):
        ctx.canvas("c", 10, 10, 42)  # type: ignore[arg-type]


def test_image_create(ctx: cui.Context) -> None:
    tex = ctx.image_create(2, 2, b"\xff\0\0\xff" * 4)
    assert tex
    run(ctx, lambda ui: ui.image(tex, width=20, height=20))
    with pytest.raises(ValueError, match="bytes"):
        ctx.image_create(2, 2, b"\0" * 15)
    ctx.image_destroy(tex)


def _pixel(ctx: cui.Context, tex: int, x: int, y: int) -> bytes:
    """Draws `tex` filling 400x300 at the top-left and reads pixel x, y."""
    run(ctx, lambda ui: ui.image(tex, width=400, height=300))
    w, _ = ctx.render_size()
    i = (y * w + x) * 4
    return ctx.render()[i : i + 4]


def test_image_update(ctx: cui.Context) -> None:
    red, green = b"\xff\0\0\xff", b"\0\xff\0\xff"
    tex = ctx.image_create(2, 2, red * 4)
    assert _pixel(ctx, tex, 100, 75) == red
    ctx.image_update(tex, 0, 0, 2, 2, green * 4)
    assert _pixel(ctx, tex, 100, 75) == green
    # a 1x2 column through a padded buffer: 12-byte rows, 4 bytes used per row
    ctx.image_update(tex, 0, 0, 1, 2, red + b"\0" * 8 + red, stride=12)
    assert _pixel(ctx, tex, 50, 75) == red
    assert _pixel(ctx, tex, 350, 75) == green


def test_image_update_rejects_bad_arguments(ctx: cui.Context) -> None:
    tex = ctx.image_create(2, 2, b"\0" * 16)
    with pytest.raises(ValueError, match="outside"):
        ctx.image_update(tex, 1, 0, 2, 2, b"\0" * 16)
    with pytest.raises(ValueError, match="outside"):
        ctx.image_update(tex, -1, 0, 1, 1, b"\0" * 4)
    with pytest.raises(ValueError, match="positive"):
        ctx.image_update(tex, 0, 0, 0, 1, b"")
    with pytest.raises(ValueError, match="stride"):
        ctx.image_update(tex, 0, 0, 2, 1, b"\0" * 8, stride=4)
    with pytest.raises(ValueError, match="bytes"):
        ctx.image_update(tex, 0, 0, 2, 2, b"\0" * 15)
    with pytest.raises(ValueError, match="not an image"):
        ctx.image_update(tex + 1000, 0, 0, 1, 1, b"\0" * 4)
    ctx.image_destroy(tex)
    with pytest.raises(ValueError, match="not an image"):
        ctx.image_update(tex, 0, 0, 1, 1, b"\0" * 4)


def test_image_functions_take_any_buffer(ctx: cui.Context) -> None:
    import array

    blue = b"\0\0\xff\xff"
    tex = ctx.image_create(2, 2, bytearray(b"\xff\0\0\xff" * 4))
    ctx.image_update(tex, 0, 0, 2, 2, memoryview(blue * 4))
    assert _pixel(ctx, tex, 100, 75) == blue
    ctx.image_update(tex, 0, 0, 2, 2, array.array("B", b"\0\xff\0\xff" * 4))
    assert _pixel(ctx, tex, 100, 75) == b"\0\xff\0\xff"
    with pytest.raises(TypeError):
        ctx.image_update(tex, 0, 0, 1, 1, "abcd")  # type: ignore[arg-type]
    with pytest.raises(BufferError):
        ctx.image_update(tex, 0, 0, 1, 1, memoryview(bytes(32))[::2])  # not contiguous
