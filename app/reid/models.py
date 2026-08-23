"""DINOv2 Re-ID model wrapper."""

from __future__ import annotations

from typing import Sequence

import torch
from PIL import Image
from transformers import AutoImageProcessor, AutoModel

from app.reid.config import BASE_MODEL_ID, MODEL_ID


class PetReIDModel(torch.nn.Module):
    def __init__(
        self,
        model_id: str = MODEL_ID,
        processor_fallback_id: str = BASE_MODEL_ID,
    ):
        super().__init__()
        self.backbone = AutoModel.from_pretrained(model_id, token=False)
        try:
            self.processor = AutoImageProcessor.from_pretrained(
                model_id,
                use_fast=True,
                token=False,
            )
            self.processor_source = model_id
        except OSError:
            self.processor = AutoImageProcessor.from_pretrained(
                processor_fallback_id,
                use_fast=True,
                token=False,
            )
            self.processor_source = processor_fallback_id

    def forward(self, images: Sequence[Image.Image]) -> torch.Tensor:
        device = next(self.parameters()).device
        inputs = self.processor(images=list(images), return_tensors="pt")
        inputs = {key: value.to(device) for key, value in inputs.items()}
        output = self.backbone(**inputs)
        return output.last_hidden_state[:, 0, :]
