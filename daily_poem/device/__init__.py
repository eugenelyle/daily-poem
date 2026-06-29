"""Device targets. One flag (config.output.target / env DAILY_POEM_TARGET) decides
whether a render goes to a PNG preview (Mac) or the Inky panel (Pi)."""
from __future__ import annotations

from pathlib import Path

from ..config import Config
from ..render.compose import Render


def output(render: Render, cfg: Config) -> Path | None:
    """Returns the preview path when previewing, None when pushing to hardware."""
    target = cfg.output.target
    if target == "preview":
        from .preview import save
        return save(render, cfg)
    if target == "inky":
        from .inky_push import push
        push(render, cfg)
        return None
    raise ValueError(f"Unknown target {target!r} (expected 'preview' or 'inky')")
