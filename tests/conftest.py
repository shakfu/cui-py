"""Shared helpers: a headless context and input that mirrors CUI's own tests."""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

import cui

Build = Callable[[cui.Context], object]


@pytest.fixture
def ctx() -> Iterator[cui.Context]:
    c = cui.Context(800, 600, reduced_motion=True)
    yield c
    c.close()


def run(ctx: cui.Context, build: Build, frames: int = 1) -> None:
    for _ in range(frames):
        with ctx.frame():
            build(ctx)


def center(r: cui.Rect) -> tuple[float, float]:
    return r.x + r.w / 2, r.y + r.h / 2


def click(ctx: cui.Context, build: Build, x: float, y: float) -> None:
    """Move, press and release, one frame each, as a user would."""
    ctx.input_mouse_move(x, y)
    run(ctx, build)
    ctx.input_mouse_button(cui.MOUSE_LEFT, True)
    run(ctx, build)
    ctx.input_mouse_button(cui.MOUSE_LEFT, False)
    run(ctx, build)


def key(ctx: cui.Context, build: Build, k: int, mods: int = 0) -> None:
    ctx.input_key(k, True, mods)
    run(ctx, build)
    ctx.input_key(k, False, mods)
    run(ctx, build)
