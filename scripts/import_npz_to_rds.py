#!/usr/bin/env python3
"""Import Colab gallery npz into BE RDS (animal_embeddings).

Typical flow after Colab section 7:

  1. Download `features/` zip from Colab before runtime disconnects
  2. Unzip locally or on EC2, e.g.:
       cache/gallery/features/gallery_features.npz
       cache/gallery/features/gallery_meta.json
       cache/gallery/features/manifest.json
  3. Run:
       export PAWPAWFIND_BACKEND_URL=http://127.0.0.1:8080
       uv run python scripts/import_npz_to_rds.py --features-dir cache/gallery/features

Dry run (no POST):
  uv run python scripts/import_npz_to_rds.py --features-dir cache/gallery/features --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _default_features_dir() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    return os.environ.get(
        "GALLERY_CACHE_ROOT",
        str(repo_root / "cache" / "gallery" / "features"),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--features-dir",
        default=_default_features_dir(),
        help="Directory containing gallery_features.npz and gallery_meta.json",
    )
    parser.add_argument("--batch-size", type=int, default=100, help="Rows per POST batch")
    parser.add_argument("--limit", type=int, default=0, help="Import only first N npz rows")
    parser.add_argument("--dry-run", action="store_true", help="Parse npz only, do not POST")
    parser.add_argument("--model-version", default=None, help="Override manifest model version")
    parser.add_argument(
        "--preprocess-version",
        default=None,
        help="Override manifest preprocess version",
    )
    args = parser.parse_args()

    from app.services.npz_import import import_npz_to_rds, resolve_features_dir

    features_dir = resolve_features_dir(args.features_dir)
    print("features_dir:", features_dir)
    print("backend_url:", os.environ.get("PAWPAWFIND_BACKEND_URL", "http://127.0.0.1:8080"))

    summary = import_npz_to_rds(
        features_dir,
        batch_size=args.batch_size,
        dry_run=args.dry_run,
        limit=args.limit,
        model_version=args.model_version,
        preprocess_version=args.preprocess_version,
    )

    print("total_rows:", summary.total_rows)
    print("prepared:", summary.prepared)
    print("skipped_missing_image_url:", summary.skipped)
    if summary.dry_run:
        print("dry_run: true (no POST)")
        return 0

    print("batches:", summary.batches)
    print("upserted:", summary.upserted)
    print("backend_skipped:", summary.backend_skipped)
    return 0 if summary.upserted > 0 or summary.prepared == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
