"""Load config.toml into typed dataclasses. One file, one source of truth."""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Page:
    orientation: str
    width: int
    height: int
    rotate_for_panel: int


@dataclass(frozen=True)
class Margins:
    top: int
    bottom: int
    left: int
    right: int


@dataclass(frozen=True)
class Type:
    body_font: str
    italic_font: str
    body_weight: int
    title_weight: int
    title_ratio: float
    author_ratio: float
    line_height: float
    line_height_min: float
    stanza_gap: float
    title_gap: float
    author_gap: float
    min_size: int
    max_size: int
    align: str
    valign: str
    valign_bias: float
    show_title: bool
    show_author: bool


@dataclass(frozen=True)
class Palette:
    file: str
    saturation: float
    mode: str


@dataclass(frozen=True)
class Source:
    backend: str            # "local" | "notion"
    dir: str
    poem: str
    notion_database_id: str = ""
    status_in: tuple[str, ...] = ()


@dataclass(frozen=True)
class Output:
    preview_path: str
    target: str


@dataclass(frozen=True)
class CompanionConfig:
    enabled: bool
    model: str
    distill_prompt: str
    rank_prompt: str
    sources: tuple[str, ...]
    candidates_per_source: int
    companion_image_path: str
    companion_json_path: str
    image_mud_threshold: float
    server_host: str
    server_port: int


@dataclass(frozen=True)
class Config:
    root: Path
    page: Page
    margins: Margins
    type: Type
    palette: Palette
    source: Source
    output: Output
    companion: CompanionConfig

    def path(self, rel: str) -> Path:
        """Resolve a config-relative path against the repo root."""
        p = Path(rel)
        return p if p.is_absolute() else (self.root / p)


def load(config_path: str | os.PathLike = "config.toml") -> Config:
    config_path = Path(config_path).resolve()
    root = config_path.parent
    with open(config_path, "rb") as fh:
        raw = tomllib.load(fh)

    companion_raw = raw.get("companion", {})
    cfg = Config(
        root=root,
        page=Page(**raw["page"]),
        margins=Margins(**raw["margins"]),
        type=Type(**raw["type"]),
        palette=Palette(**raw["palette"]),
        source=Source(**raw["source"]),
        output=Output(**raw["output"]),
        companion=CompanionConfig(
            enabled=companion_raw.get("enabled", False),
            model=companion_raw.get("model", "claude-sonnet-4-6"),
            distill_prompt=companion_raw.get("distill_prompt", "prompts/distill.md"),
            rank_prompt=companion_raw.get("rank_prompt", "prompts/rank.md"),
            sources=tuple(companion_raw.get("sources", [])),
            candidates_per_source=companion_raw.get("candidates_per_source", 3),
            companion_image_path=companion_raw.get("companion_image_path", "out/companion.png"),
            companion_json_path=companion_raw.get("companion_json_path", "out/companion.json"),
            image_mud_threshold=companion_raw.get("image_mud_threshold", 0.90),
            server_host=companion_raw.get("server_host", "0.0.0.0"),
            server_port=companion_raw.get("server_port", 8080),
        ),
    )

    # Env overrides for the operational flags that differ Mac (dev) vs Pi (deploy),
    # so the committed config stays machine-agnostic (Mac defaults to local+preview).
    target = os.environ.get("DAILY_POEM_TARGET")
    if target:
        cfg = Config(**{**cfg.__dict__, "output": Output(cfg.output.preview_path, target)})
    backend = os.environ.get("DAILY_POEM_BACKEND")
    if backend:
        cfg = Config(**{**cfg.__dict__, "source": Source(**{**cfg.source.__dict__, "backend": backend})})
    db = os.environ.get("DAILY_POEM_NOTION_DATABASE_ID")
    if db:
        cfg = Config(**{**cfg.__dict__, "source": Source(**{**cfg.source.__dict__, "notion_database_id": db})})
    return cfg
