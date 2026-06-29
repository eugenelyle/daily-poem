"""CLI entrypoint.

Commands:
  python -m daily_poem render      — pick poem, typeset, save preview or push to Inky
  python -m daily_poem companion   — run companion pipeline, save out/companion.{png,json}
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv

from . import config as config_mod
from .content import make_source
from .content.local import LocalSource
from .device import output
from .render.compose import compose


def _render(args) -> int:
    cfg = config_mod.load(args.config)

    if args.target:
        cfg = config_mod.Config(**{**cfg.__dict__,
                                   "output": config_mod.Output(cfg.output.preview_path, args.target)})

    if args.poem:
        source = LocalSource(cfg.path(cfg.source.dir), cfg.path(args.poem))
    else:
        source = make_source(cfg)
    poem = source.poem_for(args.date)

    render = compose(poem, cfg)

    for w in render.layout.warnings:
        print(f"warning: {w}", file=sys.stderr)

    result = output(render, cfg)
    where = f"preview -> {result}" if result else f"pushed to Inky (target={cfg.output.target})"
    label = poem.title or poem.meta.get("first_line") or (poem.lines[0] if poem.lines else poem.source)
    print(f'"{label}" set at {render.layout.body_size}px body; {where}')
    return 0


def _companion(args) -> int:
    from .companion import run_pipeline

    cfg = config_mod.load(args.config)

    if args.poem:
        source = LocalSource(cfg.path(cfg.source.dir), cfg.path(args.poem))
    else:
        source = make_source(cfg)
    poem = source.poem_for(date.today())

    payload = run_pipeline(poem, cfg, dry_run=args.dry_run)

    if not args.dry_run:
        kind = payload.get("type", "?")
        if kind == "image":
            print(f"companion: image from {payload.get('source_name')} -> {payload.get('image_path')}")
        elif kind == "text":
            print(f"companion: text from {payload.get('source_name')}")
        else:
            print(f"companion: blank day — buried question saved")
        json_path = cfg.path(cfg.companion.companion_json_path)
        print(f"  json -> {json_path}")

    return 0


def main(argv: list[str] | None = None) -> int:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    if "--verbose" in (argv or sys.argv):
        logging.basicConfig(level=logging.DEBUG, format="%(name)s: %(message)s")

    parser = argparse.ArgumentParser(prog="daily_poem")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="Render the poem of the day")
    r.add_argument("--config", default="config.toml")
    r.add_argument("--poem", help="Path to a specific poem file (overrides config)")
    r.add_argument("--target", choices=["preview", "inky"], help="Override output target")
    r.add_argument("--date", type=date.fromisoformat, default=date.today(),
                   help="ISO date for poem selection (default: today)")
    r.set_defaults(func=_render)

    c = sub.add_parser("companion", help="Run the companion pipeline")
    c.add_argument("--config", default="config.toml")
    c.add_argument("--poem", help="Path to a specific poem file (overrides config)")
    c.add_argument("--dry-run", action="store_true",
                   help="Print pipeline state without writing files")
    c.set_defaults(func=_companion)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
