"""A tour of the binding: forms, charts, a node graph and a live Markdown editor.

Run `python examples/showcase.py`, or `--png DIR` to save each page headless.
"""

from __future__ import annotations

import argparse
import datetime
import math
import random
from pathlib import Path

import cui

PAGES = [
    ("Controls", cui.ICON_SLIDERS_HORIZONTAL),
    ("Charts", cui.ICON_CHART_LINE),
    ("Node graph", cui.ICON_GIT_BRANCH),
    ("Editor", cui.ICON_CODE),
]

MARKDOWN = """# Release notes

CUI renders this **Markdown** as you type on the left.

- Lists, `inline code` and *emphasis*
- Tables and fenced code

| Component | Kind   |
|-----------|--------|
| button    | widget |
| dialog    | scope  |

```python
changed, value = ui.slider("Volume", value, 0, 100)
```
"""


class Showcase:
    def __init__(self) -> None:
        rng = random.Random(3)
        self.page = 0
        self.dark = False
        self.t = 0.0
        # Controls
        self.name = cui.TextBuffer(64, "Ada Lovelace")
        self.volume = 40.0
        self.gain = 0.6
        self.plan = 1
        self.size = 1
        self.when: datetime.date | None = datetime.date(2026, 11, 12)
        self.color = cui.rgb(0x6366F1)
        self.notify = True
        self.beta = False
        self.stars = 4
        self.tags = [True, False, True]
        self.dialog_open = False
        # Charts
        self.series = [
            [50 + 30 * math.sin(i / 3 + k) + rng.uniform(-6, 6) for i in range(24)]
            for k in range(2)
        ]
        self.days = [rng.random() ** 2 * 10 for _ in range(7 * 26)]
        # Node graph: id -> (title, [x, y]); links: id -> (from_pin, to_pin)
        self.view = cui.NodeView(0, 0, 1)
        self.nodes = {
            1: ("Noise", [40.0, 60.0]),
            2: ("Blur", [300.0, 30.0]),
            3: ("Output", [560.0, 120.0]),
        }
        self.links = {1: (11, 20), 2: (21, 30)}
        self.next_link = 3
        self.radius = 0.4
        # Editor
        self.doc = cui.TextBuffer(8192, MARKDOWN)
        self.ratio = 0.5

    # ---- shell ----

    def build(self, ui: cui.Context) -> None:
        self.t += ui.delta_time()
        with ui.row(width=cui.FILL, height=cui.FILL, bg=cui.COLOR_BACKGROUND):
            with ui.column(
                width=210, height=cui.FILL, pad=12, gap=2, bg=cui.COLOR_SURFACE_MUTED
            ):
                ui.heading("cui-py", 3)
                ui.text(f"CUI {cui.CUI_VERSION}", color=cui.COLOR_TEXT_MUTED)
                ui.gap(12)
                ui.nav_section("Pages")
                for i, (label, icon) in enumerate(PAGES):
                    if ui.nav_item(label, icon=icon, selected=i == self.page):
                        self.page = i
                ui.spacer()
                changed, self.dark = ui.switch("Dark theme", self.dark)
                if changed:
                    ui.set_theme(cui.THEME_DARK if self.dark else cui.THEME_LIGHT)
            with ui.column(width=cui.FILL, height=cui.FILL, pad=24, gap=16):
                ui.heading(PAGES[self.page][0], 2)
                page = [self.controls, self.charts, self.graph, self.editor][self.page]
                if page == self.charts:  # taller than the window
                    with ui.scroll(width=cui.FILL, height=cui.FILL, gap=16):
                        page(ui)
                else:
                    page(ui)

    # ---- pages ----

    def controls(self, ui: cui.Context) -> None:
        with ui.row(width=cui.FILL, gap=16, align=cui.ALIGN_START):
            with ui.card(width=cui.FILL, pad=16, gap=12):
                ui.input(
                    "name", self.name, label="Name", icon=cui.ICON_USER, clearable=True
                )
                _, self.plan = ui.select(
                    "plan", ["Free", "Pro", "Team"], self.plan, label="Plan"
                )
                _, self.when = ui.date_picker("when", self.when, label="Start date")
                _, self.volume = ui.slider(
                    "Volume", self.volume, 0, 100, step=1, show_value=True
                )
                _, self.size = ui.segmented("size", ["S", "M", "L", "XL"], self.size)
                with ui.row(gap=8):
                    for i, tag in enumerate(["python", "c99", "gpu"]):
                        _, self.tags[i] = ui.chip(tag, self.tags[i])
            with ui.card(width=cui.FILL, pad=16, gap=12):
                _, self.notify = ui.checkbox(
                    "Email me", self.notify, description="Weekly summary"
                )
                _, self.beta = ui.switch("Beta features", self.beta)
                _, self.stars = ui.rating("stars", self.stars, 5)
                with ui.row(gap=16, align=cui.ALIGN_CENTER):
                    _, self.gain = ui.knob(
                        "gain", self.gain, 0, 1, label="Gain", size=64, format="%.2f"
                    )
                    _, self.color = ui.color_picker("color", self.color)
                ui.canvas("swatch", cui.FILL, 48, self.paint_swatch(ui))
                with ui.row(gap=8):
                    if ui.button(
                        "Open dialog",
                        variant=cui.BUTTON_PRIMARY,
                        icon=cui.ICON_MESSAGE_SQUARE,
                    ):
                        self.dialog_open = True
                    if ui.button("Toast", variant=cui.BUTTON_OUTLINE):
                        who = str(self.name) or "nobody"
                        ui.toast(
                            "Saved",
                            description=f"Profile of {who}",
                            tone=cui.TONE_SUCCESS,
                        )
        with ui.dialog(
            "Hello", self.dialog_open, description="A scope whose begin can decline."
        ) as d:
            if d:
                ui.text(
                    f"Name: {self.name}, plan {['Free', 'Pro', 'Team'][self.plan]}."
                )
                with ui.dialog_footer():
                    if ui.button("Close", variant=cui.BUTTON_PRIMARY):
                        self.dialog_open = False
        self.dialog_open = self.dialog_open and d.open

    def paint_swatch(self, ui: cui.Context):  # type: ignore[no-untyped-def]
        def paint(r: cui.Rect) -> None:
            ui.draw_rect(r, 8, cui.COLOR_SURFACE)
            n = 24
            w = r.w / n
            for i in range(n):
                h = r.h * (0.3 + 0.6 * abs(math.sin(i / 3 + self.t * 2)) * self.gain)
                ui.draw_rect(
                    cui.Rect(r.x + i * w + 2, r.y + r.h - h, w - 4, h), 3, self.color
                )

        return paint

    def charts(self, ui: cui.Context) -> None:
        with ui.row(width=cui.FILL, gap=12, align=cui.ALIGN_START):
            for label, value, delta in [
                ("Revenue", "$48.2k", 12.5),
                ("Latency", "84 ms", -8.0),
                ("Uptime", "99.98%", 0.1),
            ]:
                ui.metric(label, value, delta=delta, width=cui.FILL)
        with ui.row(width=cui.FILL, gap=12, align=cui.ALIGN_START):
            with ui.card(width=cui.grow(2), pad=16, gap=8):
                ui.label("Requests per hour")
                ui.line_chart(
                    "req",
                    [
                        cui.Series("api", self.series[0]),
                        cui.Series("web", self.series[1]),
                    ],
                    height=200,
                    smooth=True,
                )
            with ui.card(width=cui.FILL, pad=16, gap=8):
                ui.label("Traffic")
                ui.donut_chart(
                    "traffic", [52, 31, 17], ["Search", "Direct", "Social"], height=200
                )
        with ui.row(width=cui.FILL, gap=12, align=cui.ALIGN_START):
            with ui.card(width=cui.FILL, pad=16, gap=8):
                ui.label("Disk usage")
                ui.treemap(
                    "disk",
                    [
                        cui.VizItem("src", 42),
                        cui.VizItem("thirdparty", 31),
                        cui.VizItem("docs", 9),
                        cui.VizItem("tests", 7),
                    ],
                    height=150,
                )
            with ui.card(width=cui.FILL, pad=16, gap=8):
                ui.label("Commits")
                ui.calendar_heatmap("commits", datetime.date(2026, 5, 11), self.days)

    def graph(self, ui: cui.Context) -> None:
        ui.text(
            "Drag nodes, drag from a pin to link, select a link and press Delete.",
            color=cui.COLOR_TEXT_MUTED,
        )
        with ui.node_editor(
            "graph", self.view, width=cui.FILL, height=cui.FILL, minimap=True
        ) as ed:
            if ed:
                for nid, (title, pos) in self.nodes.items():
                    with ui.node(nid, pos[0], pos[1], title, width=180) as nd:
                        if nid != 1:
                            ui.node_input(nid * 10, "In")
                        if nid == 2:
                            with ui.node_content():
                                _, self.radius = ui.slider(
                                    "##radius", self.radius, 0, 1
                                )
                        if nid != 3:
                            ui.node_output(nid * 10 + 1, "Out")
                    pos[:] = [nd.x, nd.y]
                for lid, (a, b) in self.links.items():
                    ui.node_link(lid, a, b)
                made, a, b = ui.node_link_created()
                if made:
                    self.links[self.next_link] = (a, b)
                    self.next_link += 1
                removed, lid = ui.node_link_removed()
                if removed:
                    self.links.pop(lid, None)
        self.view = ed.view

    def editor(self, ui: cui.Context) -> None:
        with ui.split("doc-split", self.ratio, width=cui.FILL, height=cui.FILL) as s:
            ui.code_editor(
                "doc-src", self.doc, lang="markdown", width=cui.FILL, height=10_000
            )
            ui.split_next()
            with ui.scroll(width=cui.FILL, height=cui.FILL, pad=16):
                ui.markdown("doc-view", str(self.doc), width=cui.FILL)
        self.ratio = s.ratio


def save_pages(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    app = Showcase()
    with cui.Context(1100, 720) as ctx:
        for i, (label, _) in enumerate(PAGES):
            app.page = i
            for _ in range(60):  # let transitions finish
                with ctx.frame(1 / 60):
                    app.build(ctx)
            ctx.save_png(out / f"{i}-{label.lower().replace(' ', '-')}.png")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--png", type=Path, help="save each page to this directory and exit")
    args = p.parse_args()
    if args.png:
        save_pages(args.png)
    else:
        cui.App("cui-py showcase", 1100, 720).run(Showcase().build)


if __name__ == "__main__":
    main()
