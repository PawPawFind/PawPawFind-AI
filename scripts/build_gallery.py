#!/usr/bin/env python3
"""Build shelter gallery npz cache for real /match inference.

Requires:
  uv sync --group ml
  export DATA_GO_KR_SERVICE_KEY=...
  export GALLERY_CACHE_ROOT=/var/lib/pawpawfind/gallery   # optional

This script reuses the Colab v10 gallery builder. For a full sync from the public
shelter API, run the Colab notebook once and copy the `features/` directory to EC2,
or extend this script with shelter API fetch logic from `scripts/generate_reid_modules.py`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    cache_root = os.environ.get(
        "GALLERY_CACHE_ROOT",
        str(Path(__file__).resolve().parents[1] / "cache" / "gallery"),
    )
    print("GALLERY_CACHE_ROOT:", cache_root)
    print(
        "Gallery build from shelter API is not wired in CLI yet.\n"
        "Copy Colab output to:\n"
        f"  {cache_root}/features/gallery_features.npz\n"
        f"  {cache_root}/features/gallery_meta.json\n"
        f"  {cache_root}/features/manifest.json\n"
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
