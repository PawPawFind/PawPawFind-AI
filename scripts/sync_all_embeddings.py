#!/usr/bin/env python3
"""Run shelter + report embedding batch sync together (for cron/systemd)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    python = sys.executable
    common = []
    if args.dry_run:
        common.append("--dry-run")
    if args.batch_size:
        common.extend(["--batch-size", str(args.batch_size)])
    if args.limit:
        common.extend(["--limit", str(args.limit)])

    env = os.environ.copy()
    print("backend_url:", env.get("PAWPAWFIND_BACKEND_URL", "http://127.0.0.1:8080"))

    scripts = [
        repo_root / "scripts" / "sync_animal_embeddings.py",
        repo_root / "scripts" / "sync_report_embeddings.py",
    ]
    exit_code = 0
    for script in scripts:
        cmd = [python, str(script), *common]
        print("running:", " ".join(cmd))
        result = subprocess.run(cmd, cwd=repo_root, env=env, check=False)
        if result.returncode != 0:
            exit_code = result.returncode
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
