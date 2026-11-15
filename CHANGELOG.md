# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `cui.Pty` and `ui.pty(id, p)`: a child process on a pseudo-terminal, shown by cui-repl's terminal view and emulated by libghostty-vt 1.0.0. It is behind the CMake option `CUI_PY_PTY`, off by default. It is POSIX only and needs Zig 0.17 to build. A default build compiles a stub, so `cui.Pty()` raises and `cui.PTY_AVAILABLE` is false. The view is compiled into `_core` and not a second extension module, because a second module would link its own copy of CUI and run it on contexts that `_core` created. `thirdparty/cui-repl/src/cuix.c` reads CUI 1.4.0's private `cui_internal.h`, so a CUI update can break it.

### Changed

- `make build` reuses `build/{wheel_tag}` and builds without isolation, so a rebuild recompiles only changed files. It now takes 0.6 s; it took 28 s before. In a new isolated environment, scikit-build-core deletes `CMakeCache.txt` and `CMakeFiles/`, so a persistent build directory alone did not help. `make build-pty` and `make test-asan` use their own directories, because CMake caches options and flags. `cython` and `scikit-build-core` are now in the dev group.

- Wheels target the stable ABI (`cp310-abi3`): one wheel per platform covers CPython 3.10 and later, including versions released after the build. Free-threaded builds cannot use the stable ABI and keep version-specific wheels. The build now needs Cython 3.1 or later.

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
