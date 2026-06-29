"""Content sources. `make_source` picks the backend from config; the rest of the
pipeline only sees the Source protocol (poem_for(day) -> Poem)."""
from __future__ import annotations

import os

from ..config import Config
from .base import Source


def make_source(cfg: Config) -> Source:
    if cfg.source.backend == "notion":
        from .notion import NotionSource  # lazy: only import when used
        return NotionSource(
            token=os.environ.get("NOTION_TOKEN", ""),
            database_id=cfg.source.notion_database_id,
            status_in=list(cfg.source.status_in),
        )
    from .local import LocalSource
    poem = cfg.source.poem or None
    return LocalSource(cfg.path(cfg.source.dir), cfg.path(poem) if poem else None)
