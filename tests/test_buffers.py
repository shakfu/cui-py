"""LogBuffer, TerminalBuffer and the views that read them."""

from __future__ import annotations

import threading
import time

import pytest

import cui

from .conftest import click, key, run


def lines(log: cui.LogBuffer) -> list[str]:
    return [log[i].text for i in range(len(log))]


# ---- LogBuffer ----


def test_log_append_and_read() -> None:
    log = cui.LogBuffer(8, 1024)
    log.append("one")
    log.append("two", cui.LOG_ERROR, time=12.5)
    assert len(log) == 2
    assert log[0].level == cui.LOG_INFO
    assert log[-1] == cui.LogLine(cui.LOG_ERROR, 12.5, "two")
    assert log.level_counts[cui.LOG_INFO] == 1
    assert log.level_counts[cui.LOG_ERROR] == 1
    with pytest.raises(IndexError):
        log[2]
    with pytest.raises(IndexError):
        log[-3]


def test_log_drops_oldest_when_full() -> None:
    log = cui.LogBuffer(3, 1024)
    for i in range(5):
        log.append(f"line {i}")
    assert lines(log) == ["line 2", "line 3", "line 4"]
    assert log.total == 5


def test_log_cuts_line_longer_than_text() -> None:
    log = cui.LogBuffer(4, 16)
    log.append("x" * 100)
    assert log[0].text == "x" * 15


def test_log_clear() -> None:
    log = cui.LogBuffer(4, 256)
    log.append("a")
    log.clear()
    assert len(log) == 0
    assert sum(log.level_counts) == 0


def test_log_rejects_bad_input() -> None:
    log = cui.LogBuffer(4, 256)
    with pytest.raises(ValueError):
        log.append("a", 99)
    with pytest.raises(ValueError):
        log.append("a\0b")
    with pytest.raises(ValueError):
        cui.LogBuffer(0)
    with pytest.raises(ValueError):
        cui.LogBuffer(4, 1)


# ---- TerminalBuffer ----


def test_terminal_write_lines() -> None:
    term = cui.TerminalBuffer(16, 1024)
    term.write("\x1b[31mred\x1b[0m\nplain\n")
    term.write(b"bytes\n")
    # three finished lines and the open one being written
    assert len(term) == 4
    term.clear()
    assert len(term) == 1


def test_terminal_rejects_small_buffers() -> None:
    with pytest.raises(ValueError):
        cui.TerminalBuffer(1)
    with pytest.raises(ValueError):
        cui.TerminalBuffer(16, 32)


# ---- pinning: writes after a view in the same frame wait for the paint ----


def test_log_write_after_view_waits_for_frame_end(ctx: cui.Context) -> None:
    log = cui.LogBuffer(8, 1024)
    log.append("before")
    with ctx.frame():
        ctx.log_view("log", log)
        log.append("after")
        assert lines(log) == ["before"]
    assert lines(log) == ["before", "after"]


def test_log_clear_while_pinned_drops_earlier_queued(ctx: cui.Context) -> None:
    log = cui.LogBuffer(8, 1024)
    log.append("old")
    with ctx.frame():
        ctx.log_view("log", log)
        log.append("queued")
        log.clear()
        log.append("new")
    assert lines(log) == ["new"]


def test_log_queue_is_bounded_by_capacity(ctx: cui.Context) -> None:
    log = cui.LogBuffer(4, 1024)
    with ctx.frame():
        ctx.log_view("log", log)
        for i in range(100):
            log.append(f"q{i}")
    assert lines(log) == ["q96", "q97", "q98", "q99"]


def test_terminal_write_after_view_waits_for_frame_end(ctx: cui.Context) -> None:
    term = cui.TerminalBuffer(16, 1024)
    with ctx.frame():
        ctx.terminal("term", term)
        term.write("a\nb\n")
        assert len(term) == 1
    assert len(term) == 3


def test_closing_context_applies_queued_writes() -> None:
    c = cui.Context(400, 300)
    log = cui.LogBuffer(8, 1024)
    c.begin_frame()
    c.log_view("log", log)
    log.append("queued")
    c.close()
    assert lines(log) == ["queued"]


def test_log_append_from_thread_during_frames(ctx: cui.Context) -> None:
    log = cui.LogBuffer(10_000, 1 << 20)
    n = 1000

    def writer() -> None:
        for i in range(n):
            log.append(f"{i}")
            if i % 50 == 0:
                time.sleep(0.0005)  # spread the writes over many frames

    t = threading.Thread(target=writer)
    frames = 0
    with ctx.frame():
        ctx.log_view("log", log, height=200)
        t.start()  # its first writes land while the view pins the buffer
    while t.is_alive():
        with ctx.frame():
            ctx.log_view("log", log, height=200)
        frames += 1
    t.join()
    assert frames > 5
    run(ctx, lambda ui: ui.log_view("log", log, height=200))
    assert lines(log) == [str(i) for i in range(n)]


# ---- the views ----


def test_terminal_command_is_returned_and_echoed(ctx: cui.Context) -> None:
    term = cui.TerminalBuffer(64, 4096)
    term.write("welcome\n")
    got: list[cui.TerminalResult] = []

    def build(ui: cui.Context) -> None:
        got.append(ui.terminal("term", term, height=300))

    run(ctx, build, 2)
    click(ctx, build, 400, 100)  # clicking the output focuses the input line
    ctx.input_text("ls -l")
    run(ctx, build)
    got.clear()
    key(ctx, build, cui.KEY_ENTER)
    commands = [r.command for r in got if r.command is not None]
    assert commands == ["ls -l"]
    assert len(term) > 2  # the echo


def test_log_view_renders_lines() -> None:
    def frame(log: cui.LogBuffer) -> bytes:
        c = cui.Context(600, 300, reduced_motion=True)
        for _ in range(2):
            with c.frame():
                c.log_view("log", log, height=-1, timestamps=True)
        pixels = c.render()
        c.close()
        return pixels

    empty = frame(cui.LogBuffer(8, 1024))
    log = cui.LogBuffer(8, 1024)
    for level in range(cui.LOG_LEVEL_COUNT):
        log.append(f"message {level}", level)
    assert frame(log) != empty


def test_terminal_ctrl_l_clears_buffer(ctx: cui.Context) -> None:
    # CUI clears during the build, straight into the pinned buffer
    term = cui.TerminalBuffer(64, 4096)
    term.write("a\nb\nc\n")

    def build(ui: cui.Context) -> None:
        ui.terminal("term", term, height=300)

    run(ctx, build, 2)
    click(ctx, build, 400, 100)
    key(ctx, build, cui.KEY_L, cui.MOD_CTRL)
    assert len(term) == 1
