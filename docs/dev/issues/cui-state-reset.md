# Draft: upstream issue for yappologistic/CUI

Not filed. cui-py carries the fix as `thirdparty/patches/cui-state-reset.patch`. Attach that file when filing.

---

**Title:** `cui_state` hands one component's state to another type that reuses the id

**Version:** 1.5.0 (f9597a3), also 1.4.0 (5a9c12b). macOS arm64, Apple clang.

`cui_state(ui, id, size)` returns the existing entry for `id` and grows it to `size`. It never checks that the caller is the same kind of component. If a second component type uses the same id, it reads the first one's bytes as its own struct, pointers included. In the repro, `cui__ne_dtor` frees bytes that `menu_bar` left where `cui__ne_state.set[]` keeps its arrays.

`docs/architecture.md` calls duplicate ids a caller bug. Here the result is memory corruption rather than a visual glitch, and the trigger is easy to hit:

- ids come from labels, so two components with the same label collide;
- the entry lives about 300 frames, so the two calls need not be in one frame;
- reusing a label after switching views is enough.

## Reproduction

```c
/* Build CUI with -DCUI_WITH_APP=OFF -DCMAKE_C_FLAGS=-fsanitize=address, then:
   cc -fsanitize=address -g -I include repro.c libcui.a */
#include <cui/cui.h>
#include <cui/cui_render.h>

int main(void) {
    cui_sw_renderer *sw = cui_sw_create();
    cui_ctx_desc d = { .renderer = cui_sw_iface(sw) };
    cui_ctx *ui = cui_create(&d);
    cui_node_view view = { 0 };
    for (int f = 0; f < 4; f++) {
        cui_begin_frame(ui, 1.0f / 60.0f);
        if (f < 2) {
            cui_menu_bar_begin(ui, "x", NULL);
            cui_menu_bar_end(ui);
        } else if (cui_node_editor_begin(ui, "x", &view)) {
            cui_node_editor_end(ui);
        }
        cui_end_frame(ui);
    }
    cui_destroy(ui);
    cui_sw_destroy(sw);
    return 0;
}
```

On 1.5.0:

```text
ERROR: AddressSanitizer: SEGV on unknown address 0xfffffffefffffff1
    #2 cui__default_free cui_core.c:12
    #3 cui__free cui_core.c:24
    #4 cui__ne_dtor cui_nodes.c:125
    #5 cui_destroy cui_core.c:262
    #6 main repro.c:20
```

Without ASan, the process aborts (SIGABRT, exit 134).

The reverse order is also unsafe. `menu_bar` then writes its 200 bytes over the node editor's 368-byte state, and the editor's destructor frees what it wrote.

1.5.0's state store fixes (#64) cover growth and lookup, not this.

## Proposed fix

Treat a request at a different size as a new owner. Free the old data with its destructor and start from zeroed memory:

```c
void *cui_state(cui_ctx *ui, cui_id id, size_t size) {
    cui_state_entry *e = cui__state_entry(ui, id);
    if (e->data && e->size != size) cui__state_drop_data(ui, e);  /* dtor, free, clear dtor */
    ...
```

`cui__state_drop_data` also replaces the free sequence in `cui__state_gc`. The attached patch changes 15 lines in `src/cui_core.c` and applies to 1.5.0 without offsets.

This assumes each id has one state size. I checked that two ways on 1.5.0:

- all 275 `cui_state` calls in `src/` pass a constant `sizeof`, directly or through `cui__state_lazy`;
- logging size mismatches over the cui-py test suite found none, apart from the repro's own case. That suite calls each of 421 generated wrappers at least once.

Known limits:

- Size is a proxy for type. Two types whose states have the same size still collide. A type tag argument would close that gap, at the cost of an API change.
- Two types alternating on one id within one frame now reset each other every frame. They lose state but no longer corrupt memory.
- A component that keeps a pointer to its state across a child scope would see it freed if a child of another type resolves to the same id. I found no such case. This rests on inference: scopes push an id, so a child's id differs.

A cheaper alternative is a debug-build assertion on a size mismatch. It reports the caller bug but leaves release builds unsafe.
