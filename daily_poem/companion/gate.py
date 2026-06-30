"""Step 4: render gate — walk ranked list, accept or fall through.

Text candidates are accepted immediately. Image candidates are downloaded,
quantized to the Spectra-6 palette, and quality-checked. A "muddy" image
(one where black+white combined dominate past the configured threshold) is
rejected and the gate falls through to the next ranked candidate.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

import requests
from PIL import Image

from ..config import Config
from ..render import palette as pal
from .gather import Candidate
from .rank import RankedCandidate, RankResult

log = logging.getLogger(__name__)

_TIMEOUT = 15


@dataclass
class ChosenCompanion:
    kind: str              # "text" | "image"
    buried_question: str
    lens: str
    text: str = ""         # text content (text companions)
    image: Image.Image | None = None  # clean RGB art (image companions); the page
                                       # is quantized ONCE when page 2 is composed
    source_name: str = ""
    attribution: str = ""
    url: str = ""


def gate(rank_result: RankResult, candidates: list[Candidate], cfg: Config) -> ChosenCompanion | None:
    """Walk the ranked list and return the first accepted companion, or None."""
    candidate_map = {c.id: c for c in candidates}
    panel = pal.Spectra6.load(cfg.path(cfg.palette.file))

    for ranked in rank_result.ranked:
        c = candidate_map.get(ranked.id)
        if c is None:
            log.warning("ranked candidate %s not found in pool", ranked.id)
            continue

        if c.type == "text":
            return ChosenCompanion(
                kind="text",
                buried_question=rank_result.buried_question,
                lens=ranked.lens,
                text=c.content_or_description,
                source_name=c.source_name,
                attribution=c.attribution,
                url=c.url,
            )

        if c.type == "image":
            result = _try_image(c, panel, cfg)
            if result is not None:
                return ChosenCompanion(
                    kind="image",
                    buried_question=rank_result.buried_question,
                    lens=ranked.lens,
                    image=result,
                    source_name=c.source_name,
                    attribution=c.attribution,
                    url=c.url,
                )
            log.debug("image %s failed render gate, falling through", c.id)

    return None  # blank day


def _try_image(c: Candidate, panel: pal.Spectra6, cfg: Config) -> Image.Image | None:
    """Download and quality-check. Returns clean (resized) RGB art, or None.

    The mud check quantizes a copy to judge how the art will dither; the returned
    image stays RGB so the page-2 composition quantizes exactly once.
    """
    try:
        resp = requests.get(c.image_url, timeout=_TIMEOUT,
                            headers={"User-Agent": "daily-poem/1.0"})
        resp.raise_for_status()
        rgb = Image.open(BytesIO(resp.content)).convert("RGB")
    except Exception as exc:
        log.warning("image download failed for %s: %s", c.id, exc)
        return None

    # Quantize a copy with the full 6-ink palette ONLY to judge mud — not kept.
    probe = pal.quantize(rgb, panel, cfg.palette.saturation, mode="full")
    if _is_muddy(probe, cfg.companion.image_mud_threshold):
        log.debug("image %s rejected: muddy (black+white dominant)", c.id)
        return None

    return _resize_max(rgb, 800)


def _resize_max(img: Image.Image, max_edge: int) -> Image.Image:
    """Downscale so the longest edge is <= max_edge (keeps companion.png modest)."""
    w, h = img.size
    if max(w, h) <= max_edge:
        return img
    scale = max_edge / max(w, h)
    return img.resize((round(w * scale), round(h * scale)), Image.LANCZOS)


def _is_muddy(canonical: Image.Image, threshold: float) -> bool:
    """True if black (index 0) + white (index 1) combined exceed threshold."""
    pixels = canonical.tobytes()
    total = len(pixels)
    if total == 0:
        return True
    bw = sum(1 for p in pixels if p in (0, 1))
    return bw / total > threshold
