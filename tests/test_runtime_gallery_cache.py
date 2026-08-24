import numpy as np

from app.reid.runtime import _without_report


def test_without_report_filters_only_query_report() -> None:
    gallery_data = {
        "gallery_ids": np.asarray(["animal:1", "report:42", "report:43"]),
        "record_ids": np.asarray(["1", "42", "43"]),
        "species": np.asarray(["dog", "dog", "dog"]),
        "embeddings_full": np.zeros((3, 2), dtype="float32"),
        "embeddings_crop": np.zeros((3, 2), dtype="float32"),
        "phashes_full": np.asarray(["a", "b", "c"]),
        "phashes_crop": np.asarray(["a", "b", "c"]),
        "detection_confidences": np.zeros(3, dtype="float32"),
        "blurs": np.zeros(3, dtype="float32"),
    }
    metadata = {
        "animal:1": {"candidate_report_id": None},
        "report:42": {"candidate_report_id": 42},
        "report:43": {"candidate_report_id": 43},
    }

    filtered_data, filtered_metadata = _without_report(gallery_data, metadata, 42)

    assert filtered_data["gallery_ids"].tolist() == ["animal:1", "report:43"]
    assert set(filtered_metadata) == {"animal:1", "report:43"}
