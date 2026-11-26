"""Input hooks, dispatch_input routes and focusable canvases."""

from collections.abc import Callable

import pytest

import cui


def key(k: int, down: bool = True) -> cui.InputEvent:
    return cui.InputEvent(cui.INPUT_KEY, key=k, down=down)


def recorder(
    seen: list[cui.InputEvent], result: bool
) -> Callable[[cui.InputEvent], bool]:
    """A hook that appends each event to `seen` and returns `result`."""

    def hook(e: cui.InputEvent) -> bool:
        seen.append(e)
        return result

    return hook


def focused_canvas(ctx: cui.Context) -> int:
    """Builds a component-input canvas, gives it focus, returns its id."""
    with ctx.frame():
        ctx.input_focus(True)
        ctx.canvas("c", 100, 100, focusable=True, component_input=True)
        cid = ctx.last_id()
        ctx.request_component_focus(cid)
    with ctx.frame():
        ctx.canvas("c", 100, 100, focusable=True, component_input=True)
    assert ctx.focused_id() == cid
    return cid


def test_hook_observes_and_passes_through(ctx: cui.Context) -> None:
    seen: list[cui.InputEvent] = []
    ctx.set_input_hook(recorder(seen, False))
    ctx.input_key(cui.KEY_A, True, cui.MOD_SHIFT)
    ctx.input_text("hi")
    assert seen[0] == cui.InputEvent(
        cui.INPUT_KEY, key=cui.KEY_A, down=True, mods=cui.MOD_SHIFT
    )
    assert seen[1].kind == cui.INPUT_TEXT and seen[1].text == "hi"
    assert ctx.key_down(cui.KEY_A)  # CUI still applied it
    ctx.set_input_hook(None)
    ctx.input_key(cui.KEY_B, True, 0)
    assert len(seen) == 2


def test_hook_that_returns_true_takes_the_event(ctx: cui.Context) -> None:
    ctx.set_input_hook(lambda e: True)
    ctx.input_key(cui.KEY_A, True, 0)
    assert not ctx.key_down(cui.KEY_A)


def test_route_receives_keys_for_a_focused_canvas(ctx: cui.Context) -> None:
    cid = focused_canvas(ctx)
    captured: list[cui.InputEvent] = []
    ctx.set_input_hook(recorder(captured, True))
    ctx.input_key(cui.KEY_A, True, 0)
    ctx.input_text("x")
    assert not ctx.key_down(cui.KEY_A)

    routed: list[tuple[cui.InputEvent, bool]] = []

    def route(e: cui.InputEvent) -> bool:
        routed.append((e, ctx.component_has_input(cid)))
        return e.kind == cui.INPUT_KEY

    with ctx.frame():
        for e in captured:
            ctx.dispatch_input(e, route)
        ctx.canvas("c", 100, 100, focusable=True, component_input=True)
        assert ctx.key_down(cui.KEY_A)  # physical state updates
        assert not ctx.key_action_down(cui.KEY_A)  # the route handled it
    assert [(e.kind, has) for e, has in routed] == [
        (cui.INPUT_KEY, True),
        (cui.INPUT_TEXT, True),
    ]
    assert routed[1][0].text == "x"


def test_dispatch_turns_the_hook_off_while_it_runs(ctx: cui.Context) -> None:
    calls: list[cui.InputEvent] = []
    ctx.set_input_hook(recorder(calls, True))
    with ctx.frame():
        ctx.dispatch_input(cui.InputEvent(cui.INPUT_TEXT, text="a"))  # applies the text
    assert calls == []
    ctx.input_key(cui.KEY_A, True, 0)
    assert len(calls) == 1  # restored


def test_route_cannot_build_ui_or_inject_input(ctx: cui.Context) -> None:
    with ctx.frame():
        with pytest.raises(RuntimeError, match="inside an input hook or route"):
            ctx.dispatch_input(key(cui.KEY_A), lambda e: ctx.button("x"))
        with pytest.raises(RuntimeError, match="cannot be injected"):
            ctx.dispatch_input(
                key(cui.KEY_A, False), lambda e: ctx.input_key(cui.KEY_B, True, 0)
            )
        with pytest.raises(RuntimeError, match="cannot be changed"):
            ctx.dispatch_input(key(cui.KEY_A), lambda e: ctx.set_input_hook(None))
        with pytest.raises(RuntimeError, match="inside an input hook or route"):
            ctx.dispatch_input(key(cui.KEY_A), lambda e: ctx.dispatch_input(e))
        ctx.button("after")  # the context is usable again


def test_hook_error_is_raised_at_the_next_frame(ctx: cui.Context) -> None:
    def hook(e: cui.InputEvent) -> bool:
        raise LookupError("in hook")

    ctx.set_input_hook(hook)
    ctx.input_key(cui.KEY_A, True, 0)
    assert ctx.key_down(cui.KEY_A)  # a failed hook leaves the event to CUI
    with pytest.raises(LookupError):
        ctx.begin_frame()
    assert not ctx.in_frame
    with ctx.frame():
        pass


def test_dispatch_rejects_bad_events(ctx: cui.Context) -> None:
    with pytest.raises(RuntimeError, match="inside a frame"):
        ctx.dispatch_input(key(cui.KEY_A))
    with ctx.frame():
        with pytest.raises(ValueError, match="KEY, TEXT and FOCUS"):
            ctx.dispatch_input(cui.InputEvent(cui.INPUT_MOUSE_MOVE))
        with pytest.raises(TypeError, match="needs text"):
            ctx.dispatch_input(cui.InputEvent(cui.INPUT_TEXT))
        with pytest.raises(ValueError, match="NUL"):
            ctx.dispatch_input(cui.InputEvent(cui.INPUT_TEXT, text="a\0b"))
        with pytest.raises(TypeError):
            ctx.dispatch_input(key(cui.KEY_A), route=42)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="needs focusable"):
            ctx.canvas("c", 10, 10, component_input=True)
    with pytest.raises(TypeError):
        ctx.set_input_hook(42)  # type: ignore[arg-type]


def test_focusable_canvas_is_a_tab_stop(ctx: cui.Context) -> None:
    def build(ui: cui.Context) -> None:
        ui.canvas("c", 100, 100, focusable=True)

    for _ in range(2):
        with ctx.frame():
            build(ctx)
    ctx.input_key(cui.KEY_TAB, True, 0)
    with ctx.frame():
        build(ctx)
        cid = ctx.last_id()
    assert ctx.focused_id() == cid
