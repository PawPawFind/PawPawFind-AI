from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.reid.config import CACHE_ROOT

DEFAULT_STATE_FILE = CACHE_ROOT / "sync_state.json"


@dataclass
class EmbedSyncState:
    animal_embed_synced_at: str | None = None
    report_embed_synced_at: str | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def load_sync_state(path: Path | None = None) -> EmbedSyncState:
    state_file = path or DEFAULT_STATE_FILE
    if not state_file.exists():
        return EmbedSyncState()
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    return EmbedSyncState(
        animal_embed_synced_at=payload.get("animal_embed_synced_at"),
        report_embed_synced_at=payload.get("report_embed_synced_at"),
    )


def save_sync_state(state: EmbedSyncState, path: Path | None = None) -> None:
    state_file = path or DEFAULT_STATE_FILE
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps(
            {
                "animal_embed_synced_at": state.animal_embed_synced_at,
                "report_embed_synced_at": state.report_embed_synced_at,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
