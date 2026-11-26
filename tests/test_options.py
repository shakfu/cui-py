"""Option fields that are pointers or arrays: cui.Ref and array keywords."""

import datetime

import pytest

import cui
from tests.conftest import center, click, run


def test_ref_holds_a_value_until_bound() -> None:
    r = cui.Ref(3)
    assert r.value == 3
    r.value = 4
    assert repr(r) == "Ref(4)"
    assert cui.Ref().value is None


def test_treemap_writes_the_selection(ctx: cui.Context) -> None:
    sel = cui.Ref(-1)
    rect: list[cui.Rect] = []

    def build(ui: cui.Context) -> None:
        ui.treemap("t", [cui.VizItem("a", 1.0)], width=200, height=100, selected=sel)
        rect.append(ui.last_rect())

    run(ctx, build, 2)
    assert sel.value == -1
    click(ctx, build, *center(rect[-1]))
    assert sel.value == 0  # a click selects
    click(ctx, build, *center(rect[-1]))
    assert sel.value == -1  # a second click clears


def test_ref_reads_what_the_app_set(ctx: cui.Context) -> None:
    sel = cui.Ref(0)
    run(ctx, lambda ui: ui.treemap("t", [("a", 1.0), ("b", 2.0)], selected=sel))
    sel.value = 1  # writes the bound cell
    assert sel.value == 1
    run(ctx, lambda ui: ui.treemap("t", [("a", 1.0), ("b", 2.0)], selected=sel))
    assert sel.value == 1


def test_value_struct_ref(ctx: cui.Context) -> None:
    sort = cui.Ref(cui.TableSort(1, True))
    cols = [cui.GridColumn("a", sortable=True), cui.GridColumn("b", sortable=True)]
    with ctx.frame(), ctx.data_grid("g", cols, 3, sort=sort):
        pass
    assert sort.value == cui.TableSort(1, True)
    sort.value = cui.TableSort(0, False)
    assert sort.value == cui.TableSort(0, False)


def test_ref_keeps_one_type(ctx: cui.Context) -> None:
    r = cui.Ref(False)
    run(ctx, lambda ui: ui.toolbar_button(cui.ICON_PLUS, toggle=r))
    with ctx.frame(), pytest.raises(TypeError, match="another Ref"):
        ctx.treemap("t", [("a", 1.0)], selected=r)  # type: ignore[arg-type]
    with ctx.frame(), pytest.raises(TypeError):
        ctx.treemap("t", [("a", 1.0)], selected=0)  # type: ignore[arg-type]
    with ctx.frame(), pytest.raises(TypeError):
        ctx.treemap("t", [("a", 1.0)], selected=cui.Ref("x"))  # type: ignore[arg-type]


def test_array_ref_length_follows_its_count(ctx: cui.Context) -> None:
    cols = [cui.GridColumn("a")]
    sel = cui.Ref([False, True, False])

    def grid(n: int) -> None:
        with ctx.frame(), ctx.data_grid("g", cols, n, selected=sel):
            pass

    grid(3)
    assert sel.value == [False, True, False]
    sel.value = [True] * 4  # a new length unbinds
    with pytest.raises(ValueError, match="list of 3 items, got 4"):
        grid(3)
    grid(4)
    assert sel.value == [True] * 4


def test_counted_array_sets_its_count(ctx: cui.Context) -> None:
    run(
        ctx,
        lambda ui: ui.line_chart(
            "c", [cui.Series("s", [1.0, 2.0, 3.0])], labels=["a", "b", "c"]
        ),
    )
    run(
        ctx, lambda ui: ui.line_chart("c", [cui.Series("s", [1.0, 2.0])], labels=[])
    )  # NULL, not 0
    with ctx.frame(), pytest.raises(TypeError):
        ctx.line_chart("c", [], label_count=3)  # type: ignore[call-arg]


def test_array_length_must_match_a_parameter(ctx: cui.Context) -> None:
    with ctx.frame():
        ctx.segmented("s", ["a", "b"], 0, icons=[cui.ICON_PLUS, cui.ICON_MINUS])
        with pytest.raises(ValueError, match="icons needs 2 items, got 1"):
            ctx.segmented("s", ["a", "b"], 0, icons=[cui.ICON_PLUS])
        ctx.step_slider("st", 1, 1, 3, labels=["a", "b", "c"])
        with pytest.raises(ValueError, match="labels needs"):
            ctx.step_slider("st", 1, 1, 3, labels=["a"])
        with pytest.raises(ValueError, match="labels needs 4294967296"):
            ctx.step_slider("st", 0, -(2**31), 2**31 - 1, labels=["a"])  # no int wrap
        ctx.voice_wave("w", [0.1, 0.5], owners=[cui.VOICE_YOU, cui.VOICE_REPLY])
        with pytest.raises(ValueError, match="owners needs 2"):
            ctx.voice_wave("w", [0.1, 0.5], owners=[cui.VOICE_YOU])


def test_fixed_length_array(ctx: cui.Context) -> None:
    with ctx.frame():
        days = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"]
        ctx.month_calendar("m", datetime.date(2026, 11, 1), [], day_names=days)
        with pytest.raises(ValueError, match="day_names needs 7"):
            ctx.month_calendar("m", datetime.date(2026, 11, 1), [], day_names=days[:6])


def test_single_value_pointer_and_char(ctx: cui.Context) -> None:
    with ctx.frame():
        ctx.live_cursors("c", [], view=cui.NodeView(0, 0, 1.0))
        with ctx.menu_bar("mb"):
            with ctx.menu_bar_menu("File", mnemonic="f"):
                pass
            with pytest.raises(ValueError, match="ASCII"):
                ctx.menu_bar_menu("Edit", mnemonic="ed")


def test_ref_written_after_the_call_returns(ctx: cui.Context) -> None:
    # tree_table_end writes the cursor; begin only reads it
    cur = cui.Ref(99)  # no such node
    nodes = [cui.TreeNode(-1, -1, 1, 0), cui.TreeNode(-1, -1, -1, 0)]
    cols = [cui.GridColumn("a")]
    with ctx.frame():
        with ctx.tree_table("t", cols, nodes, cursor=cur):
            assert cur.value == 99
        assert cur.value == -1
    with ctx.frame(), ctx.tree_table("t", cols, nodes, cursor=cui.Ref(0)):
        pass  # the frame keeps the unnamed Ref alive until end writes it
