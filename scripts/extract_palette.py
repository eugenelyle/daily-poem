"""Regenerate daily_poem/render/palette.json from the inky library source.

The panel palette is the library's, not ours — this keeps it that way without
hardcoding. We AST-parse inky_e673.py (rather than importing it, which would drag
in Pi-only gpiod), so this runs on a Mac too.

Usage:
  python scripts/extract_palette.py                      # fetch pinned source from GitHub
  python scripts/extract_palette.py --source path/to/inky_e673.py
"""
from __future__ import annotations

import argparse
import ast
import json
import urllib.request
from pathlib import Path

DEFAULT_URL = "https://raw.githubusercontent.com/pimoroni/inky/main/inky/inky_e673.py"
OUT = Path(__file__).resolve().parent.parent / "daily_poem" / "render" / "palette.json"
ORDER = ("BLACK", "WHITE", "YELLOW", "RED", "BLUE", "GREEN")


def _module_consts(src: str) -> tuple[dict, dict]:
    """Return ({NAME: int}, {NAME: [[r,g,b],...]}) for top-level assignments."""
    tree = ast.parse(src)
    ints, lists = {}, {}
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        try:
            value = ast.literal_eval(node.value)
        except (ValueError, SyntaxError):
            continue
        if isinstance(value, int):
            ints[target.id] = value
        elif isinstance(value, list):
            lists[target.id] = value
    return ints, lists


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", help="Local path to inky_e673.py (default: fetch from GitHub)")
    args = ap.parse_args()

    if args.source:
        src = Path(args.source).read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(DEFAULT_URL) as resp:  # noqa: S310 - pinned pimoroni URL
            src = resp.read().decode("utf-8")

    ints, lists = _module_consts(src)
    desat = lists["DESATURATED_PALETTE"][:6]
    sat = lists["SATURATED_PALETTE"][:6]
    remap = [ints[name] for name in ORDER]  # e.g. [0,1,2,3,5,6] — index 4 is skipped on the panel

    out = {
        "_provenance": f"Extracted from {args.source or DEFAULT_URL} by scripts/extract_palette.py. Do not hand-edit.",
        "panel": "Inky Impression 7.3 (Spectra 6, E673)",
        "resolution": [800, 480],
        "names": ["black", "white", "yellow", "red", "blue", "green"],
        "desaturated": desat,
        "saturated": sat,
        "hardware_remap": remap,
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT} (remap={remap})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
