"""CLI entrypoint:  python -m daily_poem render

One command: pick the poem, typeset it, and either save a preview PNG (Mac) or
push to the Inky (Pi). The target is config/env driven; companion is a no-op.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date

from . import config as config_mod
from .companion.noop import NoopCompanion
from .content import make_source
from .content.local import LocalSource
from .device import output
from .render.compose import compose


def _render(args) -> int:
    cfg = config_mod.load(args.config)

    # Per-invocation overrides (handy while iterating).
    if args.target:
        cfg = config_mod.Config(**{**cfg.__dict__,
                                   "output": config_mod.Output(cfg.output.preview_path, args.target)})

    if args.poem:  # an explicit --poem always reads a local file, regardless of backend
        source = LocalSource(cfg.path(cfg.source.dir), cfg.path(args.poem))
    else:
        source = make_source(cfg)
    poem = source.poem_for(args.date)

    companion = NoopCompanion().companion_for(poem)  # None today, by design
    render = compose(poem, cfg, companion=companion)

    for w in render.layout.warnings:
        print(f"warning: {w}", file=sys.stderr)

    result = output(render, cfg)
    where = f"preview -> {result}" if result else f"pushed to Inky (target={cfg.output.target})"
    label = poem.title or poem.meta.get("first_line") or (poem.lines[0] if poem.lines else poem.source)
    print(f'"{label}" set at {render.layout.body_size}px body; {where}')
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="daily_poem")
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="Render the poem of the day")
    r.add_argument("--config", default="config.toml")
    r.add_argument("--poem", help="Path to a specific poem file (overrides config)")
    r.add_argument("--target", choices=["preview", "inky"], help="Override output target")
    r.add_argument("--date", type=date.fromisoformat, default=date.today(),
                   help="ISO date for poem selection (default: today)")
    r.set_defaults(func=_render)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
