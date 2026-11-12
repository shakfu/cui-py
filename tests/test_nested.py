"""Components with children, and array parameters whose shape the header states only in prose."""

from typing import Any

import pytest

import cui

from .conftest import run


def test_filter_bar_has_one_mask_per_field(ctx: cui.Context) -> None:
    # selected[i] is the option mask of fields[i] (an AddressSanitizer find).
    fields = [
        cui.FilterField(name="Status", options=["Open", "Closed"]),
        {"name": "Owner", "options": ["me", "you", "them"]},
    ]
    search = cui.TextBuffer(64)
    out: list[Any] = []
    run(
        ctx, lambda ui: out.append(ui.filter_bar("f", fields, [0b01, 0b110], search)), 2
    )
    assert out[-1] == (False, [0b01, 0b110])
    with ctx.frame(), pytest.raises(ValueError, match="same length"):
        ctx.filter_bar("f", fields, [0], search)


def test_growable_array(ctx: cui.Context) -> None:
    keys = [cui.CurveKey(x=0, y=0), cui.CurveKey(x=1, y=1)]
    out: list[Any] = []
    run(ctx, lambda ui: out.append(ui.curve_editor("c", keys, 8)), 2)
    result, new_keys = out[-1]
    assert isinstance(result, cui.CurveResult)
    assert [(k.x, k.y) for k in new_keys] == [(0, 0), (1, 1)]
    with ctx.frame(), pytest.raises(ValueError, match="capacity"):
        ctx.curve_editor("c", keys, 1)


def test_event_track(ctx: cui.Context) -> None:
    out: list[Any] = []
    run(ctx, lambda ui: out.append(ui.event_track("e", [1.0, 2.5], 4, 0.0, 10.0)), 2)
    assert out[-1][1] == [1.0, 2.5]


def test_kanban(ctx: cui.Context) -> None:
    columns = {"Todo": [1, 2], "Done": [3]}
    seen: list[Any] = []

    def build(ui: cui.Context) -> None:
        with ui.kanban("board") as board:
            for title, cards in columns.items():
                with ui.kanban_column(title, len(cards)):
                    for c in cards:
                        with ui.kanban_card(c):
                            ui.text(f"card {c}")
        seen.append((board.result, board.move))

    run(ctx, build, 3)
    moved, move = seen[-1]
    assert moved is False and isinstance(move, cui.KanbanMove)


def test_node_editor(ctx: cui.Context) -> None:
    pos = {1: (40.0, 40.0), 2: (300.0, 80.0)}
    seen: list[Any] = []

    def build(ui: cui.Context) -> None:
        with ui.node_editor("graph", cui.NodeView(0, 0, 1)) as ed:
            if ed:
                for nid, (x, y) in pos.items():
                    with ui.node(nid, x, y, f"Node {nid}") as n:
                        ui.node_input(nid * 10, "in")
                        ui.node_output(nid * 10 + 1, "out")
                        with ui.node_content():
                            ui.text("body")
                    pos[nid] = (n.x, n.y)
                ui.node_link(1, 11, 20)
        seen.append(ed.view)

    run(ctx, build, 3)
    assert isinstance(seen[-1], cui.NodeView)
    assert pos[1] == (40.0, 40.0)


def test_tree_table(ctx: cui.Context) -> None:
    cols = [cui.GridColumn(title="Name", width=200)]
    # one root with one child
    nodes = [cui.TreeNode(-1, 1, -1, cui.TREE_OPEN), cui.TreeNode(0, -1, -1, 0)]
    names = ["root", "child"]
    seen: list[Any] = []

    def build(ui: cui.Context) -> None:
        with ui.tree_table("tt", cols, nodes, height=200) as tt:
            while (i := ui.tree_table_row()) >= 0:
                ui.tree_table_name(names[i], "")
        seen.append((tt.result, tt.nodes))

    run(ctx, build, 2)
    events, new_nodes = seen[-1]
    assert isinstance(events, cui.TreeTableEvents)
    assert len(new_nodes) == 2 and new_nodes[0].first_child == 1
