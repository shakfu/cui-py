"""A to-do list: the Python port of CUI's examples/todo.c.

Shows your own data as the state, a list that grows, a filter, a confirmation
dialog and saving to a file.

    python examples/todo.py [todo.txt]
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path

import cui


@dataclass
class Task:
    title: str
    done: bool = False


@dataclass
class Todo:
    path: Path | None = None
    tasks: list[Task] = field(default_factory=list)
    draft: cui.TextBuffer = field(default_factory=lambda: cui.TextBuffer(96))
    filter: int = 0  # 0 all, 1 open, 2 done
    confirm_clear: bool = False

    def load(self) -> None:
        """One task a line: "x Buy milk" when done, "- Buy milk" when not."""
        if self.path and self.path.exists():
            lines = self.path.read_text(encoding="utf-8").splitlines()
            self.tasks += [Task(ln[2:], ln[0] == "x") for ln in lines if len(ln) >= 3]

    def save(self) -> None:
        if self.path:
            text = "".join(f"{'x' if t.done else '-'} {t.title}\n" for t in self.tasks)
            self.path.write_text(text, encoding="utf-8")

    def build(self, ui: cui.Context) -> None:
        changed = False
        done = sum(t.done for t in self.tasks)
        with (
            ui.column(
                width=cui.FILL,
                height=cui.FILL,
                align=cui.ALIGN_CENTER,
                bg=cui.COLOR_BACKGROUND,
            ),
            ui.column(width=cui.FILL, max_width=560, height=cui.FILL, pad=24, gap=16),
        ):
            with ui.row(gap=12, align=cui.ALIGN_END):
                ui.heading("To do", 2)
                ui.spacer()
                ui.text(f"{len(self.tasks) - done} open, {done} done")

            # add: Enter in the field, or the button
            with ui.row(gap=8):
                typed = ui.input(
                    "new-task", self.draft, placeholder="Add a task", width=cui.FILL
                )
                add = ui.button(
                    "Add",
                    variant=cui.BUTTON_PRIMARY,
                    icon=cui.ICON_PLUS,
                    disabled=not self.draft.value,
                )
                if ((typed & cui.SUBMITTED) or add) and self.draft.value:
                    self.tasks.append(Task(self.draft.value))
                    self.draft.value = ""
                    changed = True

            with ui.row(gap=8, align=cui.ALIGN_CENTER):
                _, self.filter = ui.segmented(
                    "filter", ["All", "Open", "Done"], self.filter
                )
                ui.spacer()
                if ui.button(
                    "Clear done", variant=cui.BUTTON_GHOST, disabled=done == 0
                ):
                    self.confirm_clear = True

            # each row gets an id scope, so two tasks can have the same title
            remove = -1
            shown = 0
            with ui.scroll(id="tasks", width=cui.FILL, height=cui.FILL, gap=2):
                for i, t in enumerate(self.tasks):
                    if (self.filter == 1 and t.done) or (
                        self.filter == 2 and not t.done
                    ):
                        continue
                    shown += 1
                    with (
                        ui.id_scope(str(i)),
                        ui.row(gap=8, align=cui.ALIGN_CENTER, width=cui.FILL),
                    ):
                        toggled, t.done = ui.checkbox(t.title, t.done)
                        changed |= toggled
                        ui.spacer()
                        if ui.icon_button(
                            cui.ICON_X,
                            tooltip="Delete",
                            variant=cui.BUTTON_GHOST,
                            size=cui.SIZE_SM,
                        ):
                            remove = i
                if not shown:
                    ui.empty_state(
                        "Nothing here" if self.tasks else "No tasks yet",
                        icon=cui.ICON_LIST_CHECKS,
                        description="No task matches this filter."
                        if self.tasks
                        else "Type one above and press Enter.",
                    )
            if remove >= 0:  # after the loop, so this frame's rows match the list
                del self.tasks[remove]
                changed = True

        # the dialog shows while confirm_clear is true; closing it makes `open` false
        close = False
        with ui.dialog(
            "Clear finished tasks?",
            self.confirm_clear,
            description="They are removed from the list and from the file.",
            width=380,
        ) as d:
            if d:
                with ui.dialog_footer():
                    close = ui.button("Cancel")
                    if ui.button("Clear", variant=cui.BUTTON_DANGER):
                        self.tasks = [t for t in self.tasks if not t.done]
                        close = changed = True
                        ui.toast("Finished tasks cleared")
        self.confirm_clear = d.open and not close

        if changed:
            self.save()


def main() -> None:
    todo = Todo(Path(sys.argv[1] if len(sys.argv) > 1 else "todo.txt"))
    todo.load()
    cui.App("To do", 520, 640).run(todo.build)


if __name__ == "__main__":
    main()
