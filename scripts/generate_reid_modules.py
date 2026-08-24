"""One-shot generator: Colab notebook extract -> app/reid/*.py"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACT = ROOT / ".notebook_extracted.py"
REID = ROOT / "app" / "reid"


def chunk(name: str, text: str) -> str:
    start = text.index(f"# --- cell {name} ---")
    end = text.index("# --- cell", start + 1) if f"# --- cell" in text[start + 10 :] else len(text)
    # find next cell more reliably
    lines = text.splitlines()
    start_i = next(i for i, line in enumerate(lines) if line.strip() == f"# --- cell {name} ---")
    end_i = len(lines)
    for i in range(start_i + 1, len(lines)):
        if lines[i].startswith("# --- cell ") and not lines[i].strip().endswith(f"{name} ---"):
            end_i = i
            break
    return "\n".join(lines[start_i + 1 : end_i]).strip()


def main() -> None:
    text = EXTRACT.read_text()
    REID.mkdir(parents=True, exist_ok=True)

    cell4 = chunk("4", text)
    cell6 = chunk("6", text)
    cell12 = chunk("12", text)
    cell16 = chunk("16", text)
    cell18 = chunk("18", text)
    cell20 = chunk("20", text)

    # config.py: cell4 without colab cache bootstrap prints
    config = cell4
    config = re.sub(
        r"USE_GOOGLE_DRIVE_CACHE = False\nif USE_GOOGLE_DRIVE_CACHE:.*?\nelse:\n    CACHE_ROOT = .*?\n",
        'CACHE_ROOT = Path(__import__("os").environ.get("GALLERY_CACHE_ROOT", "/var/lib/pawpawfind/gallery"))\n',
        config,
        flags=re.S,
    )
    config = re.sub(r"IMAGE_ROOT\.mkdir\(.*?\)\n", "", config)
    config = re.sub(r"FEATURE_ROOT\.mkdir\(.*?\)\n", "", config)
    config = re.sub(r"API_PAGE_ROOT\.mkdir\(.*?\)\n", "", config)
    config = re.sub(r"print\(\"CACHE_ROOT:.*?\n", "", config)
    config = re.sub(r"print\(\"SPECIES_LIST:.*?\n", "", config)
    config = re.sub(r"print\(\"FULL SYNC:.*?\n", "", config)
    config = re.sub(r"DEVICE = .*?\n", "", config)
    config = re.sub(
        r"if torch\.cuda\.is_available\(\):.*?torch\.set_float32_matmul_precision.*?\n",
        "",
        config,
        flags=re.S,
    )
    config = re.sub(r"print\(\"DEVICE:.*?\n", "", config)
    config = re.sub(r"^import matplotlib.*\n", "", config, flags=re.M)
    config = re.sub(r"^from getpass import getpass\n", "", config, flags=re.M)
    config = config.replace("import torch\n", "")
    config = config.replace("import torch.nn.functional as F\n", "")

    (REID / "config.py").write_text(
        '"""Re-ID constants from Colab v10 notebook."""\n\n' + config + "\n"
    )

    # models.py: PetReIDModel only, no module-level init
    models = cell6
    models = re.sub(r"^reid_model = PetReIDModel\(\).*\n", "", models, flags=re.M)
    models = re.sub(r"^reid_model = reid_model\.to\(.*?\n", "", models, flags=re.M)
    models = re.sub(r"^EMBED_DIM = .*?\n", "", models, flags=re.M)
    models = re.sub(r"^detector = YOLO\(.*?\n", "", models, flags=re.M)
    models = re.sub(r"^print\(\"MODEL_ID:.*?\n", "", models, flags=re.M)
    models = re.sub(r"^print\(\"BASE_MODEL_ID:.*?\n", "", models, flags=re.M)
    models = re.sub(r"^print\(\"PROCESSOR_SOURCE:.*?\n", "", models, flags=re.M)
    models = re.sub(r"^print\(\"EMBED_DIM:.*?\n", "", models, flags=re.M)
    (REID / "models.py").write_text(
        '"""DINOv2 Re-ID model wrapper."""\n\n'
        "from __future__ import annotations\n\n" + models + "\n"
    )

    # preprocess.py
    preprocess = cell12
    preprocess = re.sub(r"def preview_photo\(.*?(?=\n# --- cell|\Z)", "", preprocess, flags=re.S)
    preprocess = preprocess.replace("reid_model(images)", "get_reid_model()(images)")
    preprocess = preprocess.replace("detector.predict", "get_detector().predict")
    (REID / "preprocess.py").write_text(
        '"""Image detection, embedding, and pHash."""\n\n'
        "from __future__ import annotations\n\n"
        "import math\n"
        "from dataclasses import dataclass\n"
        "from pathlib import Path\n"
        "from typing import Any, Dict, List, Optional, Sequence, Tuple\n\n"
        "import imagehash\n"
        "import numpy as np\n"
        "import torch\n"
        "import torch.nn.functional as F\n"
        "from PIL import Image, ImageOps\n\n"
        "from app.reid.config import (\n"
        "    COCO_CLASS_TO_SPECIES,\n"
        "    SPECIES_TO_COCO_CLASS,\n"
        "    USE_FOREGROUND_SEGMENTATION,\n"
        "    YOLO_CONFIDENCE,\n"
        ")\n"
        "from app.reid.runtime import get_detector, get_reid_model\n\n" + preprocess + "\n"
    )

    # gallery.py - functions + load helper, strip build execution
    gallery = cell16
    gallery = re.sub(
        r"\n\ngallery, gallery_meta = build_gallery_with_cache\(image_records\).*$",
        "",
        gallery,
        flags=re.S,
    )
    gallery = re.sub(
        r"for species in SPECIES_LIST:.*?print\(f\"\{species\} gallery images:.*?\)\n",
        "",
        gallery,
        flags=re.S,
    )
    gallery += """

def load_gallery_cache(cache_root: Path | None = None) -> tuple[Dict[str, np.ndarray], Dict[str, Dict[str, Any]]]:
    root = cache_root or CACHE_ROOT
    feature_root = root / "features"
    feature_file = feature_root / "gallery_features.npz"
    meta_file = feature_root / "gallery_meta.json"
    manifest_file = feature_root / "manifest.json"
    if not feature_file.exists() or not meta_file.exists():
        raise FileNotFoundError(
            f"Gallery cache not found under {feature_root}. "
            "Run scripts/build_gallery.py or set GALLERY_CACHE_ROOT."
        )
    manifest = load_json(manifest_file, {})
    from app.reid.runtime import get_embed_dim

    if manifest and not cache_is_compatible({**manifest, "embedding_dim": get_embed_dim()}):
        raise RuntimeError("Gallery cache incompatible with current model/preprocess version")
    arrays = np.load(feature_file, allow_pickle=False)
    gallery_data = {key: arrays[key] for key in arrays.files}
    metadata = load_json(meta_file, {})
    return gallery_data, metadata
"""
    (REID / "gallery.py").write_text(
        '"""Gallery npz cache load/build helpers."""\n\n'
        "from __future__ import annotations\n\n"
        "import json\n"
        "from pathlib import Path\n"
        "from typing import Any, Dict, Sequence, Tuple\n\n"
        "import numpy as np\n"
        "from tqdm.auto import tqdm\n\n"
        "from app.reid.config import CACHE_ROOT, EMBED_DIM, FEATURE_ROOT, MANIFEST_FILE, META_FILE, FEATURE_FILE, MODEL_ID, MODEL_VERSION, PREPROCESS_VERSION\n"
        "from app.reid.preprocess import image_feature_pack\n\n"
        + gallery.replace(
            'FEATURE_FILE = FEATURE_ROOT / "gallery_features.npz"',
            'FEATURE_FILE = FEATURE_ROOT / "gallery_features.npz"  # noqa: E501',
        )
        + "\n"
    )

    # search.py from cell 18
    (REID / "search.py").write_text(
        '"""Visual gallery search."""\n\nfrom __future__ import annotations\n\n' + cell18 + "\n"
    )

    # rerank.py from cell 20 (includes multimodal entry)
    rerank = cell20
    rerank = rerank.replace(
        "_text_tokenizer = None\n_text_model = None",
        "_text_tokenizer = None\n_text_model = None  # lazy text encoder",
    )
    rerank = rerank.replace("from app.reid.search import", "# uses SearchMatch from types")
    (REID / "rerank.py").write_text(
        '"""Metadata tag + text reranking."""\n\n'
        "from __future__ import annotations\n\n"
        "import re\n"
        "import unicodedata\n"
        "from dataclasses import replace\n"
        "from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple\n\n"
        "import numpy as np\n"
        "import torch\n"
        "import torch.nn.functional as F\n"
        "from transformers import AutoModel, AutoTokenizer\n\n"
        "from app.reid.config import (\n"
        "    DEFAULT_RERANK_WEIGHTS,\n"
        "    DEFAULT_TOP_K,\n"
        "    MULTIMODAL_CANDIDATE_POOL,\n"
        "    RERANK_VERSION,\n"
        "    TEXT_BATCH_SIZE,\n"
        "    TEXT_MAX_LENGTH,\n"
        "    TEXT_MODEL_ID,\n"
        ")\n"
        "from app.reid.runtime import get_device\n"
        "from app.reid.search import QueryPack, SearchMatch, search_decision, search_gallery\n\n"
        + rerank
        + "\n"
    )

    print("Generated app/reid modules")


if __name__ == "__main__":
    main()
