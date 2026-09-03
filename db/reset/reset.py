from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "db" / "seed" / "seed.py"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["D1", "D2", "D3"], required=True)
    args = parser.parse_args()
    result = subprocess.run(
        ["python3", str(SEED), "--profile", args.profile],
        cwd=ROOT,
        text=True,
        check=False,
    )
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
