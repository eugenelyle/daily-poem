"""Mac/headless target: recolour the render to look like e-ink and save a PNG.

The preview is the poem upright at composition size (e.g. 480x800 portrait) — what
you'd see hanging in the frame. The 90deg rotation to the 800x480 panel buffer
happens only on the hardware push, never here.
"""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..render import palette as pal
from ..render.compose import Render


def save(render: Render, cfg: Config, out_path: str | Path | None = None) -> Path:
    out = Path(out_path) if out_path else cfg.path(cfg.output.preview_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rgb = pal.to_preview_rgb(render.canonical, render.panel, cfg.palette.saturation)
    rgb.save(out)
    return out
