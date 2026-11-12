"""The examples, built headless for a few frames."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import cui

from .conftest import center, click, key, run

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


def load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        f"example_{name}", EXAMPLES / f"{name}.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_hello(ctx: cui.Context) -> None:
    app = load("hello").Hello()
    run(ctx, app.build, 3)


def test_dashboard(ctx: cui.Context) -> None:
    d = load("dashboard").Dashboard()
    run(ctx, d.build, 3)
    d.tab = 1
    run(ctx, d.build, 3)
    d.dark = True
    run(ctx, d.build, 2)


def test_todo_add_and_save(ctx: cui.Context, tmp_path: Path) -> None:
    mod = load("todo")
    todo = mod.Todo(tmp_path / "todo.txt")
    rect: list[cui.Rect] = []

    def build(ui: cui.Context) -> None:
        todo.build(ui)
        rect[:] = [ui.get_rect(ui.make_id("new-task"))]

    run(ctx, build, 2)
    click(ctx, build, *center(rect[0]))
    ctx.input_text("Buy milk")
    run(ctx, build)
    key(ctx, build, cui.KEY_ENTER)
    assert [t.title for t in todo.tasks] == ["Buy milk"]
    assert (tmp_path / "todo.txt").read_text() == "- Buy milk\n"
    again = mod.Todo(tmp_path / "todo.txt")
    again.load()
    assert again.tasks == todo.tasks


def test_showcase_pages(ctx: cui.Context) -> None:
    mod = load("showcase")
    app = mod.Showcase()
    for page in range(len(mod.PAGES)):
        app.page = page
        run(ctx, app.build, 3)
    app.dialog_open = True
    app.page = 0
    run(ctx, app.build, 3)


def test_showcase_console_commands(ctx: cui.Context) -> None:
    app = load("showcase").Showcase()
    app.page = 4
    before = len(app.log)
    for line in ["help", "echo hi", "log from terminal", "colors", "date", "bogus"]:
        app.run_command(line)
    assert app.log[-1].text == "from terminal"
    assert len(app.log) == before + 1
    app.run_command("worker")
    assert app.worker_on
    run(ctx, app.build, 3)
    app.run_command("worker")
    assert not app.worker_on
    app.run_command("clear")
    assert len(app.term) == 1
