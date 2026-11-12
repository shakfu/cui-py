# TODO

## Before 0.1.0

- [ ] Run the CI workflows. Linux and Windows builds have never run; MSVC with the 12 MB Cython output is unverified.
- [ ] Publish to TestPyPI (`make publish-test`) and install the wheel in a clean venv on each OS.
- [ ] Try the window interactions by hand in `examples/showcase.py`: dragging, linking, the dialog, the toast and typing in the terminal. Tests cover these only through injected input.
- [ ] Set the release date in `CHANGELOG.md` and tag `v0.1.0`.

## After 0.1.0

- [ ] File `docs/dev/upstream-cui-state-issue.md` upstream. Drop `thirdparty/patches/cui-state-reset.patch` once CUI fixes it.
- [ ] abi3 wheels (Cython 3.1+ Limited API), as in microui-py. Measure the per-call cost first.
- [ ] Positional string parameters accept `None` only where CUI documents NULL. Today every positional string rejects `None`.
- [ ] `LogBuffer.total` and `TerminalBuffer.total` undercount when writes queued during a frame overflow the buffer: the dropped writes never reach C.

## Not wrapped yet

27 functions; `docs/dev/coverage.md` has the generator's reason for each. Grouped by what blocks them:

- **Record fields the converters cannot fill.** The record converters handle scalars and strings only.
  - Pointer to another array: `cui_api_explorer_ex` (`params`), `cui_dot_chart_ex` (`values`), `cui_time_histogram_ex` (`counts`), `cui_timeline_editor_ex` (`keys`, `key_selected`, `clips`; edited in place).
  - Fixed arrays: `cui_commit_graph_ex` (`parent[2]`), `cui_waterfall_ex` (`timing[6]`), `cui_feature_flags_ex` (`on[]`, `rollout[]`; edited in place).
  - `char[N]` fields: `cui_kv_editor_ex`, `cui_url_set_params`, `cui_query_builder_ex`, `cui_query_match`, `cui_query_text`.
- **Output arrays with a caller capacity.** Return a list; pick the capacity or retry on a full result: `cui_diff_compute`, `cui_diff_view_rows`, `cui_diff_words`, `cui_url_params`, `cui_fs_list`.
- **Raw data.**
  - `cui_hex_view_ex`: bytes plus an in/out selection.
  - `cui_heatmap_ex`: a `rows * cols` matrix.
  - `cui_blame_ex`: an int array parallel to `lines`.
- **Writable strings without a capacity.** `cui_markdown_apply_task` edits text in place. `cui_otp_input` writes `length` characters.
- **Out records.** `cui_regex_search` fills a `cui_regex_match`, which has fixed-size group arrays.
- **Pointers into CUI's storage.**
  - `cui_signature_points` returns them.
  - `cui_theme_get` returns a mutable theme.
  - `cui_get_strings` and `cui_set_strings` take a translation table. The table must outlive the context.

Also: in 37 functions, some option fields are pointers and have no keyword argument, for example `cui_data_grid_begin_ex`'s `selected` and `sort`. `docs/dev/coverage.md` lists them.
