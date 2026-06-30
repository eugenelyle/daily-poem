"""Compose a poem or companion page into a panel-ready image.

Two entry points:
  compose(poem, cfg)            → page 1 (the poem), mono dither
  compose_companion(payload, cfg) → page 2 (the companion), full-colour dither

Output is a 'P'-mode image already quantized to the panel's inks (see palette.py).
"""
from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageDraw

from ..config import Config
from ..content.base import Poem
from . import palette as pal
from .layout import Layout, _wrap, layout_poem, load_font

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


def compose_companion(payload: dict, cfg: Config) -> Render:
    """Render the companion page (page 2) as a panel-ready Render.

    Flows through the same device seam as the poem page: output() previews it on
    the Mac or pushes (with rotation) to the Inky on the Pi. Quantized once here
    with the full 6-ink palette so colour art reaches the panel.

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
    empty = Layout(items=[], body_size=0, overflow=False, warnings=[])
    return Render(canonical=canonical, layout=empty, panel=panel)


# ---------------------------------------------------------------------------
# Companion layout cases
# ---------------------------------------------------------------------------

def _draw_image_companion(img, draw, payload, cfg, w, h, m) -> None:
    """Image filling the page above a bottom band of lens + attribution."""
    from pathlib import Path

    text_w = w - m.left - m.right
    lens_lines, attr_lines, lens_lh, attr_lh = _bottom_lines(payload, cfg, text_w)
    band = _band_height(lens_lines, attr_lines, lens_lh, attr_lh, m.bottom)

    art_h = h - band
    image_path = payload.get("image_path", "")
    if image_path and Path(image_path).exists():
        art = _fit(Image.open(image_path).convert("RGB"), w, art_h)
        img.paste(art, ((w - art.width) // 2, (art_h - art.height) // 2))
    else:
        draw.rectangle([0, 0, w, art_h], fill=(180, 180, 180))

    _draw_band(draw, lens_lines, attr_lines, lens_lh, attr_lh, h - band, m)


def _draw_text_companion(draw, payload, cfg, w, h, m) -> None:
    """Attribution at top, excerpt body, lens band at the bottom."""
    t = cfg.type
    text = payload.get("text", "")
    attribution = payload.get("attribution", "")
    text_w = w - m.left - m.right

    lens_lines, attr_lines, lens_lh, attr_lh = _bottom_lines(payload, cfg, text_w)
    band = _band_height(lens_lines, attr_lines, lens_lh, attr_lh, m.bottom)

    if attribution:
        attr_font = load_font(cfg.path(t.italic_font).as_posix(), _ATTR_SIZE, t.body_weight)
        for ln in _wrap(attribution, attr_font, text_w):
            draw.text((m.left, m.top), ln, font=attr_font, fill=INK_BLACK, anchor="la")
            break  # one line at top is enough

    body_font = load_font(cfg.path(t.body_font).as_posix(), 22, t.body_weight)
    body_lh = 30
    y = m.top + _ATTR_SIZE + 20
    floor = h - band - body_lh
    for raw in text.splitlines():
        for wl in _wrap(raw or " ", body_font, text_w):
            if y > floor:
                break
            draw.text((m.left, y), wl, font=body_font, fill=INK_BLACK, anchor="la")
            y += body_lh
        if y > floor:
            break

    _draw_band(draw, lens_lines, attr_lines, lens_lh, attr_lh, h - band, m)


def _draw_question_companion(draw, payload, cfg, w, h, m) -> None:
    """Buried question alone — large italic type, vertically centered."""
    t = cfg.type
    question = payload.get("buried_question", "")
    font = load_font(cfg.path(t.italic_font).as_posix(), _QUESTION_SIZE, t.title_weight)
    text_w = w - m.left - m.right

    lines = _wrap(question, font, text_w)
    line_h = _QUESTION_SIZE + 10
    total_h = len(lines) * line_h
    y = m.top + max(0, (h - m.top - m.bottom - total_h) // 2)
    for line in lines:
        lw = round(font.getlength(line))
        x = m.left + (text_w - lw) // 2
        draw.text((x, y), line, font=font, fill=INK_BLACK, anchor="la")
        y += line_h


# ---------------------------------------------------------------------------
# Shared helpers for the bottom band (lens + attribution)
# ---------------------------------------------------------------------------

def _bottom_lines(payload, cfg, text_w):
    """Wrap lens + attribution to the content width; return lines and line-heights."""
    t = cfg.type
    lens = payload.get("lens", "")
    attribution = payload.get("attribution", "")
    lens_font = load_font(cfg.path(t.italic_font).as_posix(), _LENS_SIZE, t.body_weight)
    attr_font = load_font(cfg.path(t.body_font).as_posix(), _ATTR_SIZE, t.body_weight)

    lens_lines = [(ln, lens_font) for ln in _wrap(lens, lens_font, text_w)] if lens else []
    attr_lines = [(ln, attr_font) for ln in _wrap(attribution, attr_font, text_w)] if attribution else []
    return lens_lines, attr_lines, round(_LENS_SIZE * 1.3), round(_ATTR_SIZE * 1.3)


def _band_height(lens_lines, attr_lines, lens_lh, attr_lh, bottom_margin) -> int:
    h = len(lens_lines) * lens_lh
    if attr_lines:
        h += 8 + len(attr_lines) * attr_lh
    return h + bottom_margin + 12  # 12px breathing room above the band


def _draw_band(draw, lens_lines, attr_lines, lens_lh, attr_lh, band_top, m) -> None:
    y = band_top + 12
    for ln, font in lens_lines:
        draw.text((m.left, y), ln, font=font, fill=INK_BLACK, anchor="la")
        y += lens_lh
    if attr_lines:
        y += 8
        for ln, font in attr_lines:
            draw.text((m.left, y), ln, font=font, fill=INK_BLACK, anchor="la")
            y += attr_lh


def _fit(art: Image.Image, box_w: int, box_h: int) -> Image.Image:
    """Scale to fit within the box, preserving aspect ratio."""
    aw, ah = art.size
    scale = min(box_w / aw, box_h / ah)
    return art.resize((max(1, round(aw * scale)), max(1, round(ah * scale))), Image.LANCZOS)
