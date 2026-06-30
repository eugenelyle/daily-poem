"""Step 3: poem + candidate pool → ranked list with per-candidate lenses (one LLM call).

The LLM writes a lens for EVERY ranked candidate in a single pass. If the top
image pick is later rejected by the render gate, the next candidate already has
its own lens — no second API call needed.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import anthropic

from ..config import Config
from ..content.base import Poem
from .distill import DistillResult, _format_poem, parse_json_response
from .gather import Candidate


@dataclass(frozen=True)
class RankedCandidate:
    id: str
    type: str
    source: str
    lens: str


@dataclass(frozen=True)
class RankResult:
    buried_question: str
    ranked: list[RankedCandidate]  # empty = blank day


def rank(poem: Poem, distill: DistillResult, candidates: list[Candidate], cfg: Config) -> RankResult:
    if not candidates:
        return RankResult(buried_question=distill.buried_question, ranked=[])

    template = cfg.path(cfg.companion.rank_prompt).read_text(encoding="utf-8")
    system_prompt, user_template = _parse_prompt_file(template)

    candidates_text = _format_candidates(candidates)
    user_message = (
        user_template
        .replace("{{title}}", poem.title or "")
        .replace("{{poem_text}}", _format_poem(poem))
        .replace("{{candidates}}", candidates_text)
    )

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    msg = client.messages.create(
        model=cfg.companion.model,
        max_tokens=4096,  # buried question + a lens per candidate for the whole pool
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    data = parse_json_response(msg, where="rank")
    ranked = [
        RankedCandidate(id=r["id"], type=r["type"], source=r["source"], lens=r["lens"])
        for r in data.get("ranked", [])
    ]
    return RankResult(
        buried_question=data.get("buried_question", distill.buried_question),
        ranked=ranked,
    )


def _parse_prompt_file(text: str) -> tuple[str, str]:
    """Split 'SYSTEM:\n...\n\nUSER:\n...' into (system, user) strings."""
    if "USER:" not in text:
        return "", text.strip()
    parts = text.split("USER:", 1)
    system = parts[0].replace("SYSTEM:", "", 1).strip()
    user = parts[1].strip()
    return system, user


def _format_candidates(candidates: list[Candidate]) -> str:
    lines: list[str] = []
    for c in candidates:
        lines.append(f"id: {c.id}")
        lines.append(f"type: {c.type}")
        lines.append(f"source: {c.source_name}")
        lines.append(f"content: {c.content_or_description[:400]}")
        lines.append("---")
    return "\n".join(lines)
