from __future__ import annotations

from pathlib import Path

from app.schemas.sync import AnimalForEmbeddingItem, AnimalForEmbeddingResponse
from app.services.embed_sync_state import EmbedSyncState, load_sync_state, save_sync_state
from app.services.shelter_embed_sync import sync_animal_embeddings


def test_sync_state_roundtrip(tmp_path: Path) -> None:
    state_file = tmp_path / "sync_state.json"
    save_sync_state(
        EmbedSyncState(animal_embed_synced_at="2026-08-24T00:00:00+00:00"),
        state_file,
    )
    loaded = load_sync_state(state_file)
    assert loaded.animal_embed_synced_at == "2026-08-24T00:00:00+00:00"


def test_sync_animal_embeddings_dry_run(monkeypatch) -> None:
    def fake_fetch(*, since, missing_only, timeout=120.0):
        return AnimalForEmbeddingResponse(
            items=[
                AnimalForEmbeddingItem(
                    desertionNo="111",
                    species="dog",
                    photoUrls=["https://example.com/a.jpg", "https://example.com/b.jpg"],
                )
            ]
        )

    monkeypatch.setattr(
        "app.services.shelter_embed_sync.fetch_animals_for_embedding",
        fake_fetch,
    )

    summary = sync_animal_embeddings(dry_run=True, update_state=False)
    assert summary.candidates == 1
    assert summary.prepared == 2
    assert summary.dry_run is True
