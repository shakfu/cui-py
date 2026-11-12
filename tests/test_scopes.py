"""begin/end pairs as context managers."""

from typing import Any

import pytest

import cui

from .conftest import run


def test_nesting(ctx: cui.Context) -> None:
    def build(ui: cui.Context) -> None:
        with ui.column(pad=10, gap=4) as col:
            with ui.row(gap=2):
                ui.text("a")
                ui.text("b")
            with ui.card(pad=8):
                ui.text("c")
        assert isinstance(col.value, int)  # cui_column_begin returns the box id

    run(ctx, build, 2)


def test_scope_if_false_skips_end(ctx: cui.Context) -> None:
    seen: list[Any] = []

    def build(ui: cui.Context) -> None:
        with ui.dialog("Settings", False) as d:
            seen.append((bool(d), d.open))
            if d:
                ui.text("never")

    run(ctx, build)
    assert seen == [(False, False)]


def test_scope_if_true_runs_body(ctx: cui.Context) -> None:
    seen: list[Any] = []

    def build(ui: cui.Context) -> None:
        with ui.dialog("Settings", True) as d:
            seen.append(bool(d))
            if d:
                ui.text("inside")

    run(ctx, build, 2)
    assert seen == [True, True]


def test_escape_closes_dialog(ctx: cui.Context) -> None:
    state = {"open": True}

    def build(ui: cui.Context) -> None:
        with ui.dialog("Settings", state["open"]) as d:
            if d:
                ui.text("inside")
        state["open"] = d.open

    run(ctx, build, 2)
    ctx.input_key(cui.KEY_ESCAPE, True, 0)
    run(ctx, build)
    ctx.input_key(cui.KEY_ESCAPE, False, 0)
    run(ctx, build, 2)
    assert state["open"] is False


def test_exception_inside_scope(ctx: cui.Context) -> None:
    with pytest.raises(KeyError), ctx.frame(), ctx.column(), ctx.row():
        raise KeyError("x")
    run(ctx, lambda ui: ui.text("balanced"))


def test_enter_twice(ctx: cui.Context) -> None:
    with ctx.frame():
        s = ctx.row()
        with s:
            pass
        with pytest.raises(RuntimeError, match="once"), s:
            pass


def test_out_params(ctx: cui.Context) -> None:
    seen: list[Any] = []

    def build(ui: cui.Context) -> None:
        with ui.virtual_list("vl", 1000, 20, 200) as vl:
            seen.append((vl.first, vl.last))
            for i in range(vl.first, vl.last):
                ui.text(f"row {i}")

    run(ctx, build, 2)
    first, last = seen[-1]
    assert first == 0 and 0 < last < 1000


def test_data_grid(ctx: cui.Context) -> None:
    cols = [cui.GridColumn(title="Name"), {"title": "Score", "width": 80}]
    rows = [("ann", 3), ("bob", 5)]
    seen: list[Any] = []

    def build(ui: cui.Context) -> None:
        with ui.data_grid("g", cols, len(rows)) as g:
            if g:
                seen.append((g.first, g.last))
                for r in range(g.first, g.last):
                    ui.data_grid_row(r)
                    ui.data_grid_cell_text(rows[r][0])
                    ui.data_grid_cell_text(str(rows[r][1]))

    run(ctx, build, 2)
    assert seen[-1] == (0, 2)


def test_end_result(ctx: cui.Context) -> None:
    seen: list[Any] = []

    def build(ui: cui.Context) -> None:
        with ui.reorder("r", [0, 1, 2]) as r:
            for pos in range(3):
                with ui.reorder_item(pos):
                    ui.text(f"item {pos}")
        seen.append((r.result, r.order))

    run(ctx, build, 2)
    assert seen[-1] == (False, [0, 1, 2])


def test_id_scope(ctx: cui.Context) -> None:
    def build(ui: cui.Context) -> None:
        for i in range(3):
            with ui.id_scope(str(i)):
                ui.button("Delete")

    run(ctx, build, 2)
