#!/usr/bin/env python3
"""Periodic shelter animal embedding batch sync.

Uses BE internal API to fetch changed animals, embeds photos, upserts RDS.

Examples:
  # dry-run: count targets only
  uv run python scripts/sync_animal_embeddings.py --dry-run

  # incremental (reads cache/gallery/sync_state.json since timestamp)
  uv run python scripts/sync_animal_embeddings.py

  # first gap-fill after npz import
  uv run python scripts/sync_animal_embeddings.py --missing-only
"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", default=None, help="ISO timestamp override")
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Only animals with no embedding rows yet",
    )
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-state-update", action="store_true")
    args = parser.parse_args()

    print("backend_url:", os.environ.get("PAWPAWFIND_BACKEND_URL", "http://127.0.0.1:8080"))

    from app.services.shelter_embed_sync import sync_animal_embeddings

    summary = sync_animal_embeddings(
        since=args.since,
        missing_only=args.missing_only,
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
