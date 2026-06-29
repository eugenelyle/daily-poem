"""Compose a poem or companion page into a panel-ready image.

Two entry points:
  compose(poem, cfg)            → page 1 (the poem), mono dither
  compose_companion(payload, cfg) → page 2 (the companion), full-colour dither

Output is a 'P'-mode image already quantized to the panel's inks (see palette.py).
"""
from __future__ import annotations

import textwrap
from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..config import Config
from ..content.base import Poem
from . import palette as pal
from .layout import Layout, layout_poem, load_font

INK_BLACK = (0, 0, 0)
PAPER = (255, 255, 255)

_LENS_SIZE = 18
_ATTR_SIZE = 14
_QUESTION_SIZE = 28


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

    canonical = pal.quantize(img, panel, cfg.palette.saturation, cfg.palette.mode)
    return Render(canonical=canonical, layout=layout, panel=panel)


def compose_companion(payload: dict, cfg: Config) -> Image.Image:
    """Render the companion page (page 2). Returns a preview RGB image.

    payload shapes:
      {"type": "image",    "lens": ..., "attribution": ..., "image_path": ...}
      {"type": "text",     "lens": ..., "attribution": ..., "text": ...}
      {"type": "question", "buried_question": ...}
    """
    panel = pal.Spectra6.load(cfg.path(cfg.palette.file))
    w, h = cfg.page.width, cfg.page.height
    m = cfg.margins

    img = Image.new("RGB", (w, h), PAPER)
    draw = ImageDraw.Draw(img)

    kind = payload.get("type", "question")

    if kind == "image":
        _draw_image_companion(img, draw, payload, cfg, w, h, m)
    elif kind == "text":
        _draw_text_companion(draw, payload, cfg, w, h, m)
    else:
        _draw_question_companion(draw, payload, cfg, w, h, m)

    canonical = pal.quantize(img, panel, cfg.palette.saturation, mode="full")
    return pal.to_preview_rgb(canonical, panel, cfg.palette.saturation)


# ---------------------------------------------------------------------------
# Companion layout cases
# ---------------------------------------------------------------------------

def _draw_image_companion(img, draw, payload, cfg, w, h, m) -> None:
    """Full-bleed image, lens + attribution at the bottom."""
    from pathlib import Path
    image_path = payload.get("image_path", "")
    if image_path and Path(image_path).exists():
        art = Image.open(image_path).convert("RGB")
        # Reserve bottom band for lens + attribution
        bottom_band = m.bottom + _LENS_SIZE + 8 + _ATTR_SIZE + 8
        art_h = h - bottom_band
        art = art.resize((w, art_h), Image.LANCZOS)
        img.paste(art, (0, 0))
    else:
        # Fallback: grey placeholder
        draw.rectangle([0, 0, w, h - m.bottom - _LENS_SIZE - _ATTR_SIZE - 20],
                       fill=(180, 180, 180))

    _draw_bottom_text(draw, payload, cfg, w, h, m)


def _draw_text_companion(draw, payload, cfg, w, h, m) -> None:
    """Attribution line, excerpt text, lens at bottom."""
    t = cfg.type
    text = payload.get("text", "")
    attribution = payload.get("attribution", "")

    # Attribution at top
    if attribution:
        attr_font = load_font(cfg.path(t.italic_font).as_posix(), _ATTR_SIZE, t.body_weight)
        draw.text((m.left, m.top), attribution[:80], font=attr_font, fill=INK_BLACK, anchor="la")

    # Excerpt body
    body_font = load_font(cfg.path(t.body_font).as_posix(), 22, t.body_weight)
    text_w = w - m.left - m.right
    y = m.top + _ATTR_SIZE + 20
    for line in text.splitlines():
        wrapped = textwrap.wrap(line or " ", width=max(1, int(text_w / 12)))
        for wl in wrapped:
            if y > h - m.bottom - _LENS_SIZE - 40:
                break
            draw.text((m.left, y), wl, font=body_font, fill=INK_BLACK, anchor="la")
            y += 30
        if y > h - m.bottom - _LENS_SIZE - 40:
            break

    _draw_bottom_text(draw, payload, cfg, w, h, m)


def _draw_question_companion(draw, payload, cfg, w, h, m) -> None:
    """Buried question alone — large type, vertically centered."""
    t = cfg.type
    question = payload.get("buried_question", "")
    font = load_font(cfg.path(t.italic_font).as_posix(), _QUESTION_SIZE, t.title_weight)
    text_w = w - m.left - m.right

    lines = textwrap.wrap(question, width=max(1, int(text_w / 14)))
    total_h = len(lines) * (_QUESTION_SIZE + 10)
    y = m.top + max(0, (h - m.top - m.bottom - total_h) // 2)
    for line in lines:
        lw = round(font.getlength(line))
        x = m.left + (text_w - lw) // 2
        draw.text((x, y), line, font=font, fill=INK_BLACK, anchor="la")
        y += _QUESTION_SIZE + 10


def _draw_bottom_text(draw, payload, cfg, w, h, m) -> None:
    """Lens sentence + attribution in the bottom margin."""
    t = cfg.type
    lens = payload.get("lens", "")
    attribution = payload.get("attribution", "")

    lens_font = load_font(cfg.path(t.italic_font).as_posix(), _LENS_SIZE, t.body_weight)
    attr_font = load_font(cfg.path(t.body_font).as_posix(), _ATTR_SIZE, t.body_weight)

    attr_y = h - m.bottom
    lens_y = attr_y - _LENS_SIZE - 8

    if attribution:
        draw.text((m.left, attr_y), attribution[:100], font=attr_font, fill=INK_BLACK, anchor="la")
    if lens:
        draw.text((m.left, lens_y), lens[:120], font=lens_font, fill=INK_BLACK, anchor="la")
