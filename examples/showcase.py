"""Run a synthetic Home Assistant demonstration with all network sockets blocked."""

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    return subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_showcase.py", "-s", "--log-level=ERROR"],
        cwd=root,
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())
