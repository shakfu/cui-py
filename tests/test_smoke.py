"""Every generated method, called once, in a subprocess so a crash fails the test."""

import subprocess
import sys
from pathlib import Path


def test_every_generated_method() -> None:
    script = Path(__file__).with_name("smoke_all.py")
    r = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    last = r.stdout.strip().splitlines()[-1:] if r.stdout else []
    assert r.returncode == 0, (
        f"exit {r.returncode}, last call {last}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}"
    )
    called = int(
        next(ln for ln in r.stdout.splitlines() if ln.startswith("CALLED")).split()[1]
    )
    assert called > 340
