"""The smallest app: the Python port of CUI's examples/hello.c."""

import cui


class Hello:
    def __init__(self) -> None:
        self.notifications = True
        self.clicks = 0

    def build(self, ui: cui.Context) -> None:
        with ui.column(pad=32, gap=16):
            ui.heading("Hello, CUI", 2)
            ui.secondary("A native window, a few components and no dependencies.")
            _, self.notifications = ui.switch("Notifications", self.notifications)
            with ui.row(gap=8):
                if ui.button("Click me", variant=cui.BUTTON_PRIMARY):
                    self.clicks += 1
                ui.text(f"Clicked {self.clicks} times")


def main() -> None:
    cui.App("Hello", 420, 300).run(Hello().build)


if __name__ == "__main__":
    main()
