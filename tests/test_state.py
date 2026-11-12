"""Per-id state when two component types share an id (patched cui_state)."""

import subprocess
import sys

import pytest

import cui

# case: (component kinds per phase, frames per phase)
CASES = {
    "menu-then-editor": ([["menu"], ["editor"]], 2),
    "editor-then-menu": ([["editor"], ["menu"], ["editor"]], 2),
    "same-frame": ([["menu", "editor"]], 3),
    "gc-after-swap": ([["editor"], ["menu"]], 400),
}


def run_case(case: str) -> None:
    """Build the case's frames; a corrupted state entry aborts the process."""
    phases, frames = CASES[case]
    ctx = cui.Context()
    for phase in phases:
        for _ in range(frames):
            with ctx.frame():
                for kind in phase:
                    if kind == "menu":
                        with ctx.menu_bar("x"):
                            pass
                    else:
                        with ctx.node_editor("x", {}):
                            pass
    ctx.close()


@pytest.mark.parametrize("case", CASES)
def test_shared_id_does_not_corrupt(case: str) -> None:
    # A subprocess, so an abort fails this test instead of killing pytest.
    r = subprocess.run(
        [sys.executable, __file__, case],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert r.returncode == 0, r.stderr[-2000:]


if __name__ == "__main__":
    # One case, or all in-process for `make test-asan` (macOS drops DYLD_* in subprocesses).
    for c in sys.argv[1:] or CASES:
        run_case(c)
