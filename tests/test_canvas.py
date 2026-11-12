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
