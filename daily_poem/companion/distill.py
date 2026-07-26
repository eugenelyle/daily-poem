"""Step 1: poem → buried question + oblique search angles (one LLM call)."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import anthropic

from ..config import Config
from ..content.base import Poem


@dataclass(frozen=True)
class Angle:
    """One oblique direction to search in.

    `term` is the searchable handle (1-3 words) sent verbatim to the source APIs;
    `prose` is the sentence explaining why it rhymes with the buried question.
    Every source keys off `term` — the APIs return nothing for sentence-length
    queries, which is what silently emptied the candidate pool before.
    """
    term: str
    prose: str = ""


@dataclass(frozen=True)
class DistillResult:
    buried_question: str
    angles: list[Angle]


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
        angles=parse_angles(data.get("angles", [])),
    )


def parse_angles(raw: list) -> list[Angle]:
    """Normalize the model's `angles` into Angle objects.

    Accepts the current {"term": ..., "angle": ...} shape and tolerates a bare
    string (the older shape, or a model that drifts back to it) by salvaging a
    short search term from the front of the sentence — better a rough term than
    a query no API can answer.
    """
    angles: list[Angle] = []
    for item in raw:
        if isinstance(item, dict):
            term = str(item.get("term") or "").strip()
            prose = str(item.get("angle") or item.get("prose") or "").strip()
            if not term:
                term = _salvage_term(prose)
        else:
            prose = str(item).strip()
            term = _salvage_term(prose)
        term = _clean_term(term)
        if term:
            angles.append(Angle(term=term, prose=prose))
    return angles


def _salvage_term(prose: str) -> str:
    """Take the leading concept off a prose angle ('kenosis: the emptying...')."""
    head = prose.split(":", 1)[0].split("—", 1)[0].split(",", 1)[0]
    return " ".join(head.split()[:3])


def _clean_term(term: str) -> str:
    """Strip punctuation and quoting that breaks the source APIs."""
    return term.strip().strip("'\"“”‘’.,;:—–-").strip()


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
