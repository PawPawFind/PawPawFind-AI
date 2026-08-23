#!/usr/bin/env python3
"""Periodic report photo embedding batch sync.

Embeds report photos that do not yet have report_embeddings rows.

Examples:
  uv run python scripts/sync_report_embeddings.py --dry-run
  uv run python scripts/sync_report_embeddings.py
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-process all report photos (default: missing only)",
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-state-update", action="store_true")
    args = parser.parse_args()

    print("backend_url:", os.environ.get("PAWPAWFIND_BACKEND_URL", "http://127.0.0.1:8080"))

    from app.services.report_embed_sync import sync_report_embeddings

    summary = sync_report_embeddings(
        missing_only=not args.all,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        limit=args.limit,
        update_state=not args.no_state_update,
    )

    print("candidates:", summary.candidates)
    print("prepared:", summary.prepared)
    print("skipped:", summary.skipped)
    if summary.dry_run:
        print("dry_run: true")
        return 0

    print("batches:", summary.batches)
    print("upserted:", summary.upserted)
    print("backend_skipped:", summary.backend_skipped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
