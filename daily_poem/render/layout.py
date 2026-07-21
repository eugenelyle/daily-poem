"""Typesetting: place a poem on the page as a typeset page, not terminal output.

Core rules:
  - The poet's line breaks are sacred — we never re-flow the poem into new lines.
    Auto-fit shrinks the type so the poet's lines fit as written.
  - Auto-fit: pick the largest body size at which the longest line fits the
    width AND the whole poem fits the height. Title and attribution scale with it.
  - Last resort for a line too wide even at the floor size: it is *turned* (print
    "runover") — the overflow continues flush-right on a continuation row — rather
    than clipped mid-word at the margin. Only genuinely too-tall poems then warn.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import ImageFont

from ..config import Config
from ..content.base import Poem


@dataclass
class Item:
    x: int
    y: int
    text: str
    font: ImageFont.FreeTypeFont


@dataclass
class Layout:
    items: list[Item]
    body_size: int
    overflow: bool
    warnings: list[str] = field(default_factory=list)


def load_font(path: str, size: int, weight: int, opsz: int | None = None) -> ImageFont.FreeTypeFont:
    font = ImageFont.truetype(path, size)
    try:  # variable-font axes are [Optical size, Weight]; degrade gracefully if static
        o = size if opsz is None else opsz
        font.set_variation_by_axes([max(7, min(72, o)), max(200, min(900, weight))])
    except Exception:
        pass
    return font


def _frange(start: float, stop: float, step: float):
    """Descending range of floats from `start` down to `stop` (inclusive)."""
    n = int(round((start - stop) / step))
    for i in range(n + 1):
        yield start - i * step


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_w: float) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if cur and font.getlength(trial) > max_w:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines or [""]


def _wrap_runover(text: str, font: ImageFont.FreeTypeFont, first_w: float, cont_w: float) -> list[str]:
    """Wrap so the first line fits `first_w` and any turned lines fit the (narrower)
    `cont_w` — turned lines are indented, so they have less room. The poet's words
    stay in order; used only when a line is too wide to crowd the margin as-is."""
    words = text.split()
    if not words:
        return [""]
    lines, cur, limit = [], "", first_w
    for w in words:
        trial = f"{cur} {w}".strip()
        if cur and font.getlength(trial) > limit:
            lines.append(cur)
            cur, limit = w, cont_w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


@dataclass
class _Row:
    text: str
    font: ImageFont.FreeTypeFont
    advance: int          # vertical step to the next row's top
    align: str            # "center" | "block" | "right" | "runover"


# A turned line may crowd to within this many px of the physical right edge before
# it wraps — so a line only turns when it would truly clip off the page, not merely
# because it reaches into the right margin.
_RUNOVER_INSET = 4

# A turned line's continuation hangs indented from the left margin by this many em
# (≈ 3 characters), the way verse runover is set in print.
_RUNOVER_INDENT_EM = 1.6


def _build_rows(poem: Poem, cfg: Config, size: int, text_w: int, line_height: float,
                wrap: bool = False) -> list[_Row]:
    t = cfg.type
    leading = size * line_height
    rows: list[_Row] = []

    if t.show_title and poem.title:
        ts = round(size * t.title_ratio)
        tf = load_font(cfg.path(t.italic_font).as_posix(), ts, t.title_weight, opsz=ts)
        for ln in _wrap(poem.title, tf, text_w):
            rows.append(_Row(ln, tf, round(ts * line_height), "center"))
        if rows:
            rows[-1].advance += round(leading * t.title_gap)

    bf = load_font(cfg.path(t.body_font).as_posix(), size, t.body_weight, opsz=size)
    body_align = t.align if t.align == "center" else "block"
    runover_align = "center" if t.align == "center" else "runover"
    # Turn against the FULL drawable width (left margin → near the right edge), not
    # the text measure. So a line only turns when it would truly clip off the page;
    # a line that merely reaches past the right margin just crowds it and stays put.
    wide_w = cfg.page.width - cfg.margins.left - _RUNOVER_INSET
    indent = 0 if t.align == "center" else round(size * _RUNOVER_INDENT_EM)
    for s, stanza in enumerate(poem.stanzas):
        for ln in stanza:
            # Normally one row per line (the poet's breaks are sacred). When `wrap`,
            # a line too wide even to crowd the margin is TURNED: the overflow
            # continues on an indented runover row (print convention), not clipped.
            # The first line crowds the full width; turned lines fit the indented width.
            segments = _wrap_runover(ln, bf, wide_w, wide_w - indent) if wrap else [ln]
            for i, seg in enumerate(segments):
                rows.append(_Row(seg, bf, round(leading), body_align if i == 0 else runover_align))
        if s < len(poem.stanzas) - 1 and rows:
            rows[-1].advance += round(leading * t.stanza_gap)

    # The attribution slot holds exactly one line: another poet's byline when
    # Author is set, else — for my own poems — the book the poem belongs to.
    attribution = ""
    if t.show_author and poem.author:
        attribution = f"— {poem.author}"
    elif t.show_book and not poem.author:
        book = poem.meta.get("book")
        if isinstance(book, str) and book.strip():
            attribution = f"from {book.strip()}"
    if attribution:
        au = round(size * t.author_ratio)
        af = load_font(cfg.path(t.italic_font).as_posix(), au, t.body_weight, opsz=au)
        if rows:
            rows[-1].advance += round(leading * t.author_gap)
        rows.append(_Row(attribution, af, round(au * line_height), "right"))

    return rows


def _metrics(rows: list[_Row]) -> tuple[int, int, int]:
    """(total_height, max_line_width, body_block_width)."""
    total = sum(r.advance for r in rows)
    max_w = max((round(r.font.getlength(r.text)) for r in rows), default=0)
    block_w = max((round(r.font.getlength(r.text)) for r in rows if r.align == "block"), default=0)
    return total, max_w, block_w


def layout_poem(poem: Poem, cfg: Config) -> Layout:
    m, t, p = cfg.margins, cfg.type, cfg.page
    text_w = p.width - m.left - m.right
    text_h = p.height - m.top - m.bottom

    def fits(rows: list[_Row]) -> bool:
        total_h, max_w, _ = _metrics(rows)
        return max_w <= text_w and total_h <= text_h

    # Stage 1: largest body size that fits at the airy default leading.
    chosen, lead, rows, overflow = t.min_size, t.line_height, [], True
    for size in range(t.max_size, t.min_size - 1, -1):
        rows = _build_rows(poem, cfg, size, text_w, t.line_height)
        if fits(rows):
            chosen, overflow = size, False
            break

    # Stage 2: still overflowing at the floor — tighten leading before clipping.
    if overflow:
        for lh in (round(x * 100) / 100 for x in _frange(t.line_height, t.line_height_min, 0.02)):
            trial = _build_rows(poem, cfg, t.min_size, text_w, lh)
            if fits(trial):
                chosen, lead, rows, overflow = t.min_size, lh, trial, False
                break
        else:  # too wide to fit even at the floor: turn over-wide lines (runover)
            lead = t.line_height_min
            rows = _build_rows(poem, cfg, t.min_size, text_w, lead, wrap=True)

    # Recompute against the PAGE, not the text area: a turned line may crowd the
    # right margin, and a poem may spill into the bottom margin — both still on-page.
    # A residual overflow now means something truly clips off the page edge.
    total_h, max_w, block_w = _metrics(rows)
    draw_w, draw_h = p.width - m.left, p.height - m.top
    overflow = max_w > draw_w or total_h > draw_h
    warnings: list[str] = []
    if overflow:
        warnings.append(
            f"Poem does not fit at min size {t.min_size}px even with tightest leading "
            f"(needs {max_w}x{total_h}px, have {draw_w}x{draw_h}px on-page). Placed anyway."
        )

    if t.valign == "top":
        y = m.top
    elif t.valign == "optical":
        # Place the block's centre at valign_bias of the text area. Long poems
        # (total_h ~ text_h) clamp to the top margin; short poems sit a little high.
        y = m.top + max(0, round(text_h * t.valign_bias - total_h / 2))
    else:  # center
        y = m.top + max(0, (text_h - total_h) // 2)
    block_x = m.left + max(0, (text_w - block_w) // 2)
    items: list[Item] = []
    for r in rows:
        w = round(r.font.getlength(r.text))
        if r.align == "center":
            x = m.left + (text_w - w) // 2
        elif r.align == "runover":  # turned line: hanging indent from the left margin
            x = block_x + round(r.font.size * _RUNOVER_INDENT_EM)
        elif r.align == "right":
            x = p.width - m.right - w
        else:  # block: left-aligned lines inside a horizontally-centred block
            x = block_x
        items.append(Item(x, y, r.text, r.font))
        y += r.advance

    return Layout(items=items, body_size=chosen, overflow=overflow, warnings=warnings)
