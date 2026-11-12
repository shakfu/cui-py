# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Bindings for CUI 1.4.0, vendored in `thirdparty/cui` and linked statically. `tools/gen_bindings.py` generates them from CUI's headers with libclang: 353 Context methods, 48 of them scopes, and 17 functions. The output is committed, so a build needs only Cython and a C compiler. A generator, rather than hand-written wrappers, because CUI has 476 public functions and changes between minor releases. `docs/dev/coverage.md` lists what is not wrapped.
- `cui.App`, a native window with an event loop. It releases the GIL while it waits for events.
- `cui.Context()` without a window: software rendering, `render()`, `save_png()`, input injection and a clipboard, for tests.
- `ctx.canvas(id, w, h, paint)` with `draw_*` methods that work only inside `paint`. An exception raised in `paint` is re-raised when the frame ends.
- `examples/hello.py`, `examples/todo.py`, `examples/dashboard.py` and `examples/showcase.py`.

### Fixed

- Vendored CUI patch: a component that reused another component type's id read that type's state struct as its own, and `cui_destroy` later freed pointers from it (abort on macOS). `cui_state` now discards an entry asked for at a different size. Reset over a debug assertion, because the collision follows from repeated labels in release builds too. See `docs/dev/known-issues.md`.

### Removed

- The template's `add` and `greet` functions.

## [0.1.0] - 2026-11-12

### Added

- Initial project structure
- Core module with example functions
- Test suite with pytest
- Build system using scikit-build-core
