"""Step 5: persist the chosen companion (or buried question) to disk.

Writes:
  out/companion.json  — always written (lens, attribution, buried question, type)
  out/companion.png   — written only when kind="image" (already quantized)

The companion.json shape is also used by the button-press server to know which
page-2 render to produce.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..config import Config
from .gate import ChosenCompanion


def emit(companion: ChosenCompanion | None, buried_question: str, cfg: Config) -> dict:
    """Save companion files; return the JSON payload for logging/dry-run."""
    img_path = cfg.path(cfg.companion.companion_image_path)
    json_path = cfg.path(cfg.companion.companion_json_path)
    img_path.parent.mkdir(parents=True, exist_ok=True)

    if companion is None:
        payload = {
            "type": "question",
            "buried_question": buried_question,
        }
    elif companion.kind == "image":
        # Save the clean RGB art; page 2 quantizes once when it's composed.
        companion.image.save(img_path)
        payload = {
            "type": "image",
            "buried_question": companion.buried_question,
            "lens": companion.lens,
            "attribution": companion.attribution,
            "source_name": companion.source_name,
            "url": companion.url,
            "image_path": str(img_path),
        }
    else:  # text
        payload = {
            "type": "text",
            "buried_question": companion.buried_question,
            "lens": companion.lens,
            "text": companion.text,
            "attribution": companion.attribution,
            "source_name": companion.source_name,
            "url": companion.url,
        }

    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload
