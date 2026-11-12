"""Generated component wrappers: arguments, options, outputs and records."""

import datetime
from typing import Any

import pytest

import cui

from .conftest import center, click, key, run


def test_button_click(ctx: cui.Context) -> None:
    clicks = []
    rect: list[cui.Rect] = []

    def build(ui: cui.Context) -> None:
        with ui.column(pad=20):
            if ui.button("Save", variant=cui.BUTTON_PRIMARY):
                clicks.append(1)
            rect[:] = [ui.last_rect()]

    run(ctx, build, 2)
    click(ctx, build, *center(rect[0]))
    assert clicks == [1]
    run(ctx, build, 3)
    assert clicks == [1]


def test_checkbox_returns_new_value(ctx: cui.Context) -> None:
    state = {"on": False}
    rect: list[cui.Rect] = []

    def build(ui: cui.Context) -> None:
        with ui.column(pad=20):
            _, state["on"] = ui.checkbox("Remember", state["on"])
            rect[:] = [ui.last_rect()]

    run(ctx, build, 2)
    click(ctx, build, rect[0].x + 8, rect[0].y + rect[0].h / 2)
    assert state["on"] is True


def test_text_input_and_clipboard(ctx: cui.Context) -> None:
    buf = cui.TextBuffer(64, "hi")
    rect: list[cui.Rect] = []

    def build(ui: cui.Context) -> None:
        with ui.column(pad=20):
            ui.input("name", buf, placeholder="Name")
            rect[:] = [ui.last_rect()]

    run(ctx, build, 2)
    click(ctx, build, rect[0].x + 10, rect[0].y + rect[0].h / 2)
    key(ctx, build, cui.KEY_END)
    ctx.input_text(" there")
    run(ctx, build, 2)
    assert buf.value == "hi there"
    key(ctx, build, cui.KEY_A, cui.MOD_PRIMARY)
    key(ctx, build, cui.KEY_C, cui.MOD_PRIMARY)
    assert ctx.clipboard == "hi there"


def test_input_respects_capacity(ctx: cui.Context) -> None:
    buf = cui.TextBuffer(4, "")
    rect: list[cui.Rect] = []

    def build(ui: cui.Context) -> None:
        ui.input("x", buf)
        rect[:] = [ui.last_rect()]

    run(ctx, build, 2)
    click(ctx, build, *center(rect[0]))
    ctx.input_text("abcdefgh")
    run(ctx, build, 2)
    assert buf.value == "abc"


def test_unknown_option(ctx: cui.Context) -> None:
    with ctx.frame(), pytest.raises(TypeError):
        ctx.button("x", nonsense=1)  # type: ignore[call-arg]


def test_bad_values(ctx: cui.Context) -> None:
    with ctx.frame():
        with pytest.raises(ValueError, match="0..255"):
            ctx.button("x", color=(300, 0, 0))
        with pytest.raises(ValueError, match="NUL"):
            ctx.button("a\0b")
        with pytest.raises(TypeError):
            ctx.button(None)  # type: ignore[arg-type]
        with pytest.raises(TypeError):
            ctx.slider("s", "high", 0, 1)  # type: ignore[arg-type]


def test_sizes_and_colors(ctx: cui.Context) -> None:
    def build(ui: cui.Context) -> None:
        with ui.row(width=cui.FILL, height=40, bg=cui.COLOR_SURFACE_MUTED, gap=4):
            ui.button("a", width=cui.pct(50), color=0x336699)
            ui.button("b", width=120, color=(1, 2, 3))

    run(ctx, build, 2)


def test_string_lists(ctx: cui.Context) -> None:
    out: list[Any] = []

    def build(ui: cui.Context) -> None:
        out[:] = [
            ui.select("fruit", ["apple", "pear"], 1, label="Fruit"),
            ui.tabs("t", ["One", "Two", "Three"], 2),
        ]

    run(ctx, build, 2)
    assert out == [(False, 1), (False, 2)]


def test_inout_array(ctx: cui.Context) -> None:
    out: list[Any] = []
    run(
        ctx,
        lambda ui: out.append(
            ui.toggle_group("tg", ["B", "I", "U"], [True, False, True])
        ),
    )
    assert out[0] == (False, [True, False, True])
    with ctx.frame(), pytest.raises(ValueError, match="same length"):
        ctx.toggle_group("tg", ["B", "I"], [True])


def test_float_list(ctx: cui.Context) -> None:
    run(ctx, lambda ui: ui.sparkline([1, 3, 2, 5], 100, 20, cui.COLOR_ACCENT))
    run(ctx, lambda ui: ui.donut_chart("d", [1, 2], ["a", "b"]))
    with ctx.frame(), pytest.raises(ValueError, match="same length"):
        ctx.donut_chart("d", [1, 2], ["a"])


def test_records_as_dict_tuple_or_namedtuple(ctx: cui.Context) -> None:
    items = [
        {"label": "a", "value": 3},
        cui.VizItem(label="b", value=5),
        ("c", 1.0, 0xFF0000),
    ]
    run(ctx, lambda ui: ui.bar_list("bl", items))
    with ctx.frame():
        with pytest.raises(TypeError, match="no field"):
            ctx.bar_list("bl", [{"lable": "a"}])
        with pytest.raises(TypeError, match="at most"):
            ctx.bar_list("bl", [("a", 1, 2, 3)])


def test_record_with_nested_array(ctx: cui.Context) -> None:
    series = [
        cui.Series(name="s", values=[1, 2, 3]),
        {"name": "t", "values": [3, 2, 1]},
    ]
    run(ctx, lambda ui: ui.line_chart("lc", series, height=120))


def test_mutable_records(ctx: cui.Context) -> None:
    steps = [cui.CheckStep(title="One", done=True), cui.CheckStep(title="Two")]
    out: list[Any] = []
    run(ctx, lambda ui: out.append(ui.checklist("cl", steps)))
    _, new_steps = out[0]
    assert [s.title for s in new_steps] == ["One", "Two"]
    assert [s.done for s in new_steps] == [True, False]


def test_dates(ctx: cui.Context) -> None:
    d = datetime.date(2026, 11, 12)
    out: list[Any] = []
    run(ctx, lambda ui: out.append(ui.date_picker("d", d)))
    assert out[0] == (False, d)
    out.clear()
    run(ctx, lambda ui: out.append(ui.date_picker("d2", None)))
    assert out[0] == (False, None)


def test_result_struct(ctx: cui.Context) -> None:
    out: list[Any] = []
    run(ctx, lambda ui: out.append(ui.path_bar("pb", ["home", "user"])))
    r = out[0]
    assert isinstance(r, cui.PathBarResult)
    assert (r.clicked, r.submitted, r.editing) == (-1, None, False)


def test_strlen_param(ctx: cui.Context) -> None:
    m = ctx.measure_text(cui.FONT_BODY, 14, "hello")
    assert m.width > 0
    assert ctx.measure_text(cui.FONT_BODY, 14, "hello hello").width > m.width


def test_toast(ctx: cui.Context) -> None:
    out: list[Any] = []
    run(ctx, lambda ui: out.append(ui.toast("Saved", description="All good")))
    assert isinstance(out[0], int)
    run(ctx, lambda ui: None, 3)  # CUI copied the title; our bytes are gone
