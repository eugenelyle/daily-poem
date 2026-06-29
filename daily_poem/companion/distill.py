"""Step 1: poem → buried question + oblique search angles (one LLM call)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import anthropic

from ..config import Config
from ..content.base import Poem


@dataclass(frozen=True)
class DistillResult:
    buried_question: str
    angles: list[str]


def distill(poem: Poem, cfg: Config) -> DistillResult:
    template = cfg.path(cfg.companion.distill_prompt).read_text(encoding="utf-8")
    prompt = (
        template
        .replace("{{title}}", poem.title or "")
        .replace("{{poem_text}}", _format_poem(poem))
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=cfg.companion.model,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = msg.content[0].text.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0].strip()

    data = json.loads(raw)
    return DistillResult(
        buried_question=data["buried_question"],
        angles=data["angles"],
    )


def _format_poem(poem: Poem) -> str:
    parts: list[str] = []
    for i, stanza in enumerate(poem.stanzas):
        parts.extend(stanza)
        if i < len(poem.stanzas) - 1:
            parts.append("")
    return "\n".join(parts)
