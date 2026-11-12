"""Call every generated Context method once with plausible arguments.

Every string is unique: CUI keys state by id, and two component types that
share an id read each other's state (docs/dev/known-issues.md).

Run by test_smoke.py in a subprocess, so a crash fails the test instead of
killing pytest. Prints each method name before the call; the last name printed
is the one that crashed. Exits 1 if any call raised.
"""

from __future__ import annotations

import ast
import datetime
import sys
from pathlib import Path
from typing import Any

import cui

STUB = Path(cui.__file__).with_name("_core.pyi")
N = 2  # length of every sequence, so arrays that share a count agree

VALUES: dict[str, Any] = {
    "str": "x",
    "int": 0,
    "float": 10.0,
    "bool": False,
    "ColorLike": (10, 20, 30),
    "SizeLike": 50,
    "RectLike": (0, 0, 10, 10),
    "Vec2Like": (1, 1),
    "CornersLike": 2,
    "DateLike": datetime.date(2026, 1, 1),
    "TextBuffer": None,  # a fresh one per call
    "Sequence[str]": ["a", "b"],
    "Sequence[float]": [1.0, 2.0],
    "Sequence[int]": [0, 1],
    "Sequence[bool]": [False, True],
}


def value(ann: str, tag: str) -> Any:
    if ann == "str":
        return tag
    if ann == "TextBuffer":
        return cui.TextBuffer(64, "abc")
    if ann in VALUES:
        return VALUES[ann]
    if ann.startswith("Sequence[") and ann[9:-1] in VALUES:
        return [VALUES[ann[9:-1]]] * N
    if ann.startswith("Sequence["):
        return [{} for _ in range(N)]
    if ann.endswith("| Collection[Any]"):
        return {}
    raise KeyError(ann)


def methods() -> list[tuple[str, list[tuple[str, str]], str]]:
    tree = ast.parse(STUB.read_text())
    gen = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "_GenContext"
    )
    out = []
    for f in gen.body:
        if isinstance(f, ast.FunctionDef):
            args = [
                (a.arg, ast.unparse(a.annotation))
                for a in f.args.args[1:]
                if a.annotation is not None
            ]
            out.append((f.name, args, ast.unparse(f.returns) if f.returns else "None"))
    return out


def main() -> int:
    failures = []
    ctx = cui.Context(800, 600, reduced_motion=True)
    calls = 0
    for name, anns, ret in methods():
        args = [
            8 if arg in ("capacity", "cap") else value(a, f"{name}.{i}")
            for i, (arg, a) in enumerate(anns)
        ]
        fn = getattr(ctx, name)
        print(name, flush=True)
        try:
            if name.startswith(("draw_", "push_clip", "pop_clip")):
                if name == "pop_clip":
                    continue

                def paint(r: cui.Rect, fn: Any = fn, args: list[Any] = args) -> None:
                    fn(*args)
                    if fn.__name__ == "push_clip":
                        ctx.pop_clip()

                with ctx.frame():
                    ctx.canvas("c", 100, 100, paint)
            elif ret.endswith("Scope"):
                for _ in range(2):
                    with ctx.frame(), fn(*args):
                        pass
            else:
                for _ in range(2):
                    with ctx.frame():
                        fn(*args)
            calls += 1
        except Exception as e:  # noqa: BLE001
            failures.append(f"{name}: {type(e).__name__}: {e}")
    ctx.close()
    print(f"CALLED {calls}")
    for f in failures:
        print("FAILED", f)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
