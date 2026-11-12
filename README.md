# cui-py

Cython bindings for [CUI](https://github.com/yappologistic/CUI), an immediate-mode UI library in C99 with about 190 components. The distribution is `cui-py`; the import name is `cui`.

CUI 1.4.0 is vendored in `thirdparty/cui` and compiled into the extension, so there are no runtime dependencies. Linux needs the X11 development headers to build (`libx11-dev`).

Status: alpha. Tested on macOS (Cocoa, arm64, CPython 3.14). The CI workflows build on Linux and Windows, but those builds have not run yet.

```python
import cui

clicks = 0

def frame(ui: cui.Context) -> None:
    global clicks
    with ui.column(pad=32, gap=16):
        ui.heading("Hello, CUI", 2)
        if ui.button("Click me", variant=cui.BUTTON_PRIMARY):
            clicks += 1
        ui.text(f"Clicked {clicks} times")

cui.App("Hello", 420, 300).run(frame)
```

`examples/` has `hello.py`, `todo.py` (a port of CUI's tutorial app), `dashboard.py` and `showcase.py` (forms, charts, a node graph, a live Markdown editor and a console; `--png DIR` saves each page headless).

## Install

```bash
git clone <this repo> && cd cui-py
uv sync          # builds the extension
make test
```

## How the C API maps to Python

- **Names.** `cui_button_ex` is `ui.button`. `CUI_BUTTON_PRIMARY` is `cui.BUTTON_PRIMARY`. Icons are strings: `cui.ICON_PLUS`.
- **Options.** The fields of a C options struct become keyword-only arguments. An argument you leave out keeps CUI's default.
- **Outputs.** A pointer the component writes to becomes a return value, after the component's own result:

  ```python
  changed, value = ui.checkbox("Remember me", value)
  changed, index = ui.select("fruit", ["apple", "pear"], index)
  ```

- **Text fields.** A text field edits a `cui.TextBuffer(capacity, value)` in place. Capacity counts bytes, including the trailing NUL, as in C.
- **Log and terminal.** `ui.log_view` reads a `cui.LogBuffer` and `ui.terminal` a `cui.TerminalBuffer`. Both are rings that drop the oldest lines when full, and any thread may write to them:

  ```python
  log = cui.LogBuffer(lines=4096)
  log.append("disk almost full", cui.LOG_WARN)    # from any thread
  ui.log_view("log", log, timestamps=True)

  r = ui.terminal("term", term)
  if r.command is not None:
      term.write(f"\x1b[32mran\x1b[0m {r.command}\n")
  ```

  A write made after the view in the same frame shows from the next frame. CUI cannot be woken from another thread, so call `ui.request_wakeup(seconds)` while a thread is writing.
- **Lists.** A list of strings or floats replaces a C array and its count. A list of records replaces an array of structs. Each record can be a namedtuple (`cui.VizItem(label="a", value=3)`), a tuple, or a dict. Missing fields are zero.
- **Containers.** A begin/end pair is a context manager. When `begin` can decline, as a closed dialog does, the scope is falsy and `end` is skipped:

  ```python
  with ui.dialog("Settings", open) as d:
      if d:
          ui.text("inside")
  open = d.open
  ```

  The scope exposes the pair's outputs as attributes (`d.open`, `vl.first`). The value `end` returns is in `.result`.
- **Values.**
  - Colors: `0xRRGGBB`, `(r, g, b[, a])`, `cui.rgb()`, or theme tokens such as `cui.COLOR_ACCENT`.
  - Sizes: a number in points, `cui.FILL`, `cui.pct(50)` or `cui.grow(2)`.
  - Dates: `datetime.date`, or `None` for unset.
- **Drawing.** `ui.canvas(id, width, height, paint)` calls `paint(rect)` after layout. Only there do the `draw_*` methods work.

`cui.Context()` with no window renders headless with CUI's software renderer. Its parts:

- input arrives through `ui.input_*`
- `render()` and `save_png()` read the pixels
- copy and paste use `ctx.clipboard`

The tests use this.

## Errors instead of crashes

Misuse that would be undefined behaviour in C raises an exception:

- building outside a frame
- building inside a paint callback
- drawing outside one
- ending a frame with a scope open
- using a closed context
- passing strings with NUL characters
- passing arrays of unequal length
- passing color channels outside 0..255
- writing more text than a buffer holds

Strings and arrays passed to CUI stay alive until the frame is painted.

The vendored CUI carries one patch, for state shared by two component types with one id. A narrower case remains; see [docs/dev/known-issues.md](docs/dev/known-issues.md).

## Coverage

The generator wraps 372 entries: 355 Context methods, including 48 scopes, and 17 module functions. Another 35 functions are wrapped by hand. [docs/dev/coverage.md](docs/dev/coverage.md) lists the 27 functions not wrapped yet and why, and the options that have no keyword argument.

## Development

`tools/gen_bindings.py` reads CUI's headers with libclang and writes these files:

- `src/cui/_cui.pxd`
- `src/cui/_gen.pxi`
- `src/cui/_core.pyi`
- `docs/dev/coverage.md`

The output is committed. Run `make gen` after updating `thirdparty/cui`. Hand-written code lives in `src/cui/_core.pyx`.

| Target | |
|-|-|
| `make build` | rebuild the extension |
| `make test` | headless tests, including one call to every generated method |
| `make test-window` | also open a hidden window |
| `make test-asan` | tests under AddressSanitizer (macOS) |
| `make qa` | lint, format check, mypy, tests |

## License

MIT. The vendored CUI is MIT, with its fonts under OFL (Inter, Geist) and ISC (Lucide). See `thirdparty/cui/LICENSE`, `thirdparty/cui/THIRD_PARTY.md` and `thirdparty/cui/assets/fonts/`.
