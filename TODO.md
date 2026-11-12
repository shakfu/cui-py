# TODO

## Critical

- [ ] File `docs/dev/upstream-cui-state-issue.md` upstream. Drop `thirdparty/patches/cui-state-reset.patch` once CUI fixes it.

## High

- [ ] Run the CI workflows. Linux and Windows builds have never run; MSVC with the 12 MB Cython output is unverified.
- [ ] Log console and terminal: `cui_log_buffer` and `cui_terminal_buffer` need owning Python classes (9 functions).

## Medium

- [ ] abi3 wheels (Cython 3.1+ Limited API), as in microui-py. Measure the per-call cost first.
- [ ] Output arrays with a caller capacity: `cui_diff_compute`, `cui_diff_view_rows`, `cui_diff_words`, `cui_url_params`.
- [ ] Records with `char[N]` fields (`cui_kv_pair`) and with nested struct arrays (`cui_dot_series`, `cui_commit`, `cui_net_request`).
- [ ] Options that are pointers, such as `cui_grid_opts.selected` and `.sort`. Listed in `docs/dev/coverage.md`.

## Low

- [ ] `cui_set_strings` for translated component text. The table must outlive the context.
- [ ] Positional string parameters accept `None` only where CUI documents NULL. Today every positional string rejects `None`.
