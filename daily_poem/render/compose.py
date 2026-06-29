"""Compose a poem (+ optional companion) into the final panel-ready image.

Output is a 'P'-mode image already quantized to the panel's inks (see palette.py).
The device layer consumes this directly — it does not re-dither.
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..config import Config
from ..content.base import Poem
from . import palette as pal
from .layout import Layout, layout_poem

INK_BLACK = (0, 0, 0)
PAPER = (255, 255, 255)


@dataclass
class Render:
    canonical: Image.Image      # 'P' image, 6-colour canonical palette, panel composition size
    layout: Layout
    panel: pal.Spectra6


def compose(poem: Poem, cfg: Config, companion=None) -> Render:
    panel = pal.Spectra6.load(cfg.path(cfg.palette.file))
    layout = layout_poem(poem, cfg)

    img = Image.new("RGB", (cfg.page.width, cfg.page.height), PAPER)
    draw = ImageDraw.Draw(img)
    for item in layout.items:
        draw.text((item.x, item.y), item.text, font=item.font, fill=INK_BLACK, anchor="la")

    # Companion hook — intentionally inert. The editorial layer lands here later
    # (an image/quote region beneath or beside the poem). It is a no-op today.
    if companion is not None:
        _draw_companion(img, draw, companion, cfg)

    canonical = pal.quantize(img, panel, cfg.palette.saturation, cfg.palette.mode)
    return Render(canonical=canonical, layout=layout, panel=panel)


def _draw_companion(img, draw, companion, cfg) -> None:  # pragma: no cover - stub
    """Reserved for the editorial companion. No-op until that module is built."""
    return
