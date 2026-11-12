# Known issues

## Two component types with state of equal size can share an id (CUI 1.4.0)

CUI keeps per-id state that any component can claim. Stock CUI 1.4.0 hands an
existing entry to whichever component asks next. A second type with the same
id then reads the first one's struct and can free its pointers.

cui-py patches `cui_state` to discard an entry requested at a different size
(`thirdparty/patches/cui-state-reset.patch`, tests in `tests/test_state.py`).
Size stands in for type, so two types whose state structs have equal size
still share an entry. Give components of different types distinct labels, or
wrap them in `ctx.id_scope(...)`.

The upstream report is drafted in [upstream-cui-state-issue.md](upstream-cui-state-issue.md).
