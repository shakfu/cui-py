# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0]

### Added

- `cui.Pty` and `ui.pty(id, p)`: a child process on a pseudo-terminal, shown by cui-repl's terminal view and emulated by libghostty-vt 1.0.0. It is behind the CMake option `CUI_PY_PTY`, off by default. It is POSIX only and needs Zig 0.17 to build. A default build compiles a stub, so `cui.Pty()` raises and `cui.PTY_AVAILABLE` is false. The view is compiled into `_core` and not a second extension module, because a second module would link its own copy of CUI and run it on contexts that `_core` created. `thirdparty/cui-repl/src/cuix.c` calls CUI's public API for focus queries, the cursor and the clipboard, and reads the private `cui_internal.h` for text, keys, Tab, setting focus and the wheel, so a CUI update can break it.

- Window state and placement on `App`: `maximize`, `minimize`, `restore`, `window_state`, `set_position`, `placement` and `follow_system_theme`, and `App(placement=...)` to reopen a window where it was. `placement()` returns a `cui.WindowPlacement`. CUI clamps a placement's size to the minimum size.

- `ctx.image_update(tex, x, y, width, height, rgba, stride=0)` replaces a region of an image texture in place, for video and camera frames. It takes only textures from this context's `image_create` or `image_load`. Handles are plain ints, and an R8 font-atlas handle would make the OpenGL renderer read four times the buffer. `rgba` is any C-contiguous buffer, such as `bytes`, a `memoryview` or a NumPy array; `image_create` takes the same.

- Component input: `ctx.canvas(..., focusable=True, component_input=True)` makes a canvas a Tab stop that receives keys and text. `ctx.set_input_hook(fn)` sees each `cui.InputEvent` before CUI and can take it, and `ctx.dispatch_input(event, route)` replays it to `route(event)`. `dispatch_input` turns the hook off while it runs: CUI requires this, because a replayed TEXT event otherwise reaches the hook again. Building UI, injecting input or changing the hook inside a hook or route raises `RuntimeError`, as CUI forbids them there. An exception in a hook is raised at the next frame boundary.

- Option fields that are pointers or arrays now have keywords. 12 of 84 remain: callbacks, a buffer without a size, and two structs cui-py cannot convert (`docs/dev/coverage.md`). A field C reads and writes takes a `cui.Ref`, such as `ui.treemap(..., selected=sel)` with `sel = cui.Ref(-1)`. A `Ref` owns the storage C points at and lives until the frame ends, because some components write it later: a tree table writes `cursor` in `tree_table_end`. An array takes a sequence, and its count field is set from `len()`. An array whose length comes from a parameter or is fixed raises `ValueError` on any other length, since C reads that many entries. Each field is listed by hand in `tools/gen_bindings.py`: a pointer that looks like one value can be an array, as `data_grid`'s `selected` is.

  ```python
  sel = cui.Ref(-1)
  ui.treemap("t", items, selected=sel)
  ui.segmented("view", ["List", "Board"], i, icons=[cui.ICON_LIST, cui.ICON_LAYOUT_DASHBOARD])
  ```

  The count keywords these arrays now set are gone, such as `label_count`, `place_count`, `tick_count` and `meter_channels`.

### Changed

- CUI 1.5.0 ([release notes](https://github.com/yappologistic/CUI/releases/tag/v1.5.0)). The generator wraps 421 entries, up from 372, and 48 more are written by hand, up from 35; `docs/dev/coverage.md` lists the 34 not wrapped yet. `ctx.spinner(size, ...)` now takes `cui_spinner_ex`'s options, such as `style` and `color`. Charts, gauges and the series palette draw differently, and the radial gauge has no needle. `cui-state-reset.patch` is regenerated against 1.5.0, which keeps the `cui_state` behaviour it fixes.

- `make build` reuses `build/{wheel_tag}` and builds without isolation, so a rebuild recompiles only changed files. It now takes 0.6 s; it took 28 s before. In a new isolated environment, scikit-build-core deletes `CMakeCache.txt` and `CMakeFiles/`, so a persistent build directory alone did not help. `make build-pty` and `make test-asan` use their own directories, because CMake caches options and flags. `cython` and `scikit-build-core` are now in the dev group.

- Wheels target the stable ABI (`cp311-abi3`): one wheel per platform covers CPython 3.11 and later, including versions released after the build. 3.11 over 3.10 because the buffer protocol joined the stable ABI in 3.11, and `image_update` would otherwise copy each frame through `bytes`. Python 3.10 is no longer supported. Free-threaded builds cannot use the stable ABI and keep version-specific wheels. The build now needs Cython 3.1 or later.

## [0.1.0]

First release.

### Added

- Bindings for CUI 1.4.0, vendored in `thirdparty/cui` and linked statically. `tools/gen_bindings.py` generates them from CUI's headers with libclang: 355 Context methods, 48 of them scopes, and 17 functions; 35 more are written by hand. The output is committed, so a build needs only Cython and a C compiler. A generator, rather than hand-written wrappers, because CUI declares 496 functions and changes between minor releases. `docs/dev/coverage.md` lists the 27 functions not wrapped yet.

- `cui.App`, a native window with an event loop. It releases the GIL while it waits for events.

- `cui.Context()` without a window: software rendering, `render()`, `save_png()`, input injection and a clipboard, for tests.

- `ctx.canvas(id, w, h, paint)` with `draw_*` methods that work only inside `paint`. An exception raised in `paint` is re-raised when the frame ends.

- `cui.LogBuffer` and `cui.TerminalBuffer` for `ui.log_view` and `ui.terminal`. Any thread may write to them. CUI paints line text straight from the buffer after the build returns, and `App.frame()` releases the GIL meanwhile, so a write from another thread could change text mid-paint. A view therefore pins its buffer until the frame ends and queues writes made until then, capped at the buffer's capacity. Queueing over a lock, because a lock held across `App.frame()` would also be held while it waits for input and block the writer.

- `examples/hello.py`, `examples/todo.py`, `examples/dashboard.py` and `examples/showcase.py`.

- `make test-asan`: the tests and a call to every generated method under AddressSanitizer (macOS).

### Fixed

- Vendored CUI patch: a component that reused another component type's id read that type's state struct as its own, and `cui_destroy` later freed pointers from it (abort on macOS). `cui_state` now discards an entry asked for at a different size. Reset over a debug assertion, because the collision follows from repeated labels in release builds too. See `docs/dev/known-issues.md`.
