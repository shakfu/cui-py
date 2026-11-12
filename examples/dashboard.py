"""A dashboard: tabs, metrics, charts, a data grid and a canvas you paint yourself."""

from __future__ import annotations

import math
import random

import cui

COLUMNS = [
    cui.GridColumn(title="Region", width=160, sortable=True),
    cui.GridColumn(title="Orders", width=100, align=cui.TEXT_END, sortable=True),
    cui.GridColumn(title="Revenue", width=120, align=cui.TEXT_END),
]


class Dashboard:
    def __init__(self, seed: int = 7) -> None:
        rng = random.Random(seed)
        self.tab = 0
        self.dark = False
        self.weekly = [rng.uniform(20, 80) for _ in range(12)]
        self.rows = [
            (f"Region {i:03d}", rng.randint(10, 999), rng.uniform(1e3, 9e4))
            for i in range(2000)
        ]
        self.t = 0.0

    def paint_wave(self, ui: cui.Context, r: cui.Rect) -> None:
        ui.draw_rect(r, 8, cui.COLOR_SURFACE_MUTED)
        pts = [
            (r.x + r.w * i / 63, r.y + r.h / 2 + math.sin(i / 6 + self.t) * r.h / 3)
            for i in range(64)
        ]
        ui.draw_polyline(pts, 2, cui.COLOR_ACCENT, False)

    def build(self, ui: cui.Context) -> None:
        self.t += ui.delta_time()
        with ui.column(
            width=cui.FILL, height=cui.FILL, pad=24, gap=16, bg=cui.COLOR_BACKGROUND
        ):
            with ui.row(gap=12, align=cui.ALIGN_CENTER, width=cui.FILL):
                ui.heading("Larkspur", 2)
                ui.spacer()
                changed, self.dark = ui.switch("Dark", self.dark)
                if changed:
                    ui.set_theme(cui.THEME_DARK if self.dark else cui.THEME_LIGHT)
            _, self.tab = ui.tabs("tabs", ["Overview", "Orders"], self.tab)
            if self.tab == 0:
                self.overview(ui)
            else:
                self.orders(ui)

    def overview(self, ui: cui.Context) -> None:
        with ui.row(gap=12, width=cui.FILL):
            for label, value, delta in [
                ("Revenue", "$48.2k", 12.5),
                ("Orders", "1,284", -3.1),
                ("Users", "9,301", 4.0),
            ]:
                with ui.card(width=cui.FILL, pad=16):
                    ui.metric(label, value, delta=delta)
        with ui.row(gap=12, width=cui.FILL):
            with ui.card(width=cui.grow(2), pad=16, gap=8):
                ui.label("Weekly orders")
                ui.line_chart(
                    "weekly",
                    [cui.Series(name="Orders", values=self.weekly)],
                    height=180,
                )
            with ui.card(width=cui.FILL, pad=16, gap=8):
                ui.label("Channels")
                ui.bar_list(
                    "channels",
                    [
                        cui.VizItem("Search", 52),
                        cui.VizItem("Direct", 31),
                        cui.VizItem("Social", 17),
                    ],
                )
        ui.canvas("wave", cui.FILL, 80, lambda r: self.paint_wave(ui, r))
        ui.request_wakeup(1 / 30)  # the wave animates

    def orders(self, ui: cui.Context) -> None:
        with ui.data_grid(
            "orders", COLUMNS, len(self.rows), height=cui.FILL, striped=True
        ) as g:
            if g:
                for i in range(g.first, g.last):
                    region, orders, revenue = self.rows[i]
                    ui.data_grid_row(i)
                    ui.data_grid_cell_text(region)
                    ui.data_grid_cell_text(f"{orders:,}")
                    ui.data_grid_cell_text(f"${revenue:,.0f}")


def main() -> None:
    cui.App("Dashboard", 1000, 720).run(Dashboard().build)


if __name__ == "__main__":
    main()
