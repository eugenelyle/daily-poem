"""Companion pipeline: distill → gather → rank → gate → emit.

Entry point: run_pipeline(poem, cfg, dry_run=False)
"""
from __future__ import annotations

import logging

from ..config import Config
from ..content.base import Poem
from .distill import distill
from .emit import emit
from .gate import gate
from .gather import gather
from .rank import rank

log = logging.getLogger(__name__)


def run_pipeline(poem: Poem, cfg: Config, *, dry_run: bool = False) -> dict:
    """Run the full companion pipeline. Returns the emitted JSON payload.

    With dry_run=True, prints pipeline state at each step and skips file writes.
    """
    log.info("distilling poem: %s", poem.title or poem.lines[0][:40])
    distill_result = distill(poem, cfg)

    if dry_run:
        print(f"\n=== BURIED QUESTION ===\n{distill_result.buried_question}")
        print(f"\n=== OBLIQUE ANGLES ===")
        for a in distill_result.angles:
            print(f"  • {a}")

    log.info("gathering candidates from %d sources", len(cfg.companion.sources))
    candidates = gather(distill_result.angles, cfg)

    if dry_run:
        print(f"\n=== CANDIDATE POOL ({len(candidates)} candidates) ===")
        for c in candidates:
            print(f"  [{c.type}] {c.source_name}: {c.content_or_description[:80].replace(chr(10), ' ')}")

    log.info("ranking %d candidates", len(candidates))
    rank_result = rank(poem, distill_result, candidates, cfg)

    if dry_run:
        print(f"\n=== RANKED ({len(rank_result.ranked)} candidates) ===")
        for i, r in enumerate(rank_result.ranked):
            print(f"  {i+1}. [{r.type}] {r.source}")
            print(f"     lens: {r.lens}")

    log.info("running render gate")
    chosen = gate(rank_result, candidates, cfg)

    if dry_run:
        print("\n=== RENDER GATE ===")
        if chosen is None:
            print("  result: BLANK DAY (no candidate passed gate)")
        else:
            print(f"  result: ACCEPTED [{chosen.kind}] from {chosen.source_name}")
            print(f"  lens:   {chosen.lens}")
            if chosen.kind == "image":
                print(f"  image size: {chosen.image.size}")

    if dry_run:
        print("\n=== DRY RUN — no files written ===")
        return {
            "type": chosen.kind if chosen else "question",
            "buried_question": rank_result.buried_question,
            "lens": chosen.lens if chosen else None,
        }

    payload = emit(chosen, rank_result.buried_question, cfg)
    return payload
