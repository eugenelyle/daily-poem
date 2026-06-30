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

    data = parse_json_response(msg, where="distill")
    return DistillResult(
        buried_question=data["buried_question"],
        angles=data["angles"],
    )


def message_text(msg) -> str:
    """Concatenate all text blocks (robust to non-text or multi-block responses)."""
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")


def parse_json_response(msg, where: str) -> dict:
    """Extract a JSON object from an LLM message, tolerating prose/fences.

    Raises with the raw response (and stop_reason) so a bad reply is never a
    silent 'Expecting value' — you see exactly what the model said.
    """
    text = message_text(msg)
    raw = text.strip()
    if raw.startswith("```"):  # ```json ... ```
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    start, end = raw.find("{"), raw.rfind("}")
    if start != -1 and end > start:
        raw = raw[start:end + 1]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{where}: model did not return JSON "
            f"(stop_reason={getattr(msg, 'stop_reason', '?')}): {text[:600]!r}"
        ) from exc


def _format_poem(poem: Poem) -> str:
    parts: list[str] = []
    for i, stanza in enumerate(poem.stanzas):
        parts.extend(stanza)
        if i < len(poem.stanzas) - 1:
            parts.append("")
    return "\n".join(parts)
