"""Local-export poem source: a folder of .md (or .json) files.

Markdown format — optional `---` frontmatter of `key: value` scalars, then the
poem body. Blank lines separate stanzas; every other newline is a line break the
poet chose, and we keep it. If no `title:` is given, a leading `# Heading` is used.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .base import Poem, daily_pick, is_index_title


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    block = text[3:end].strip("\n")
    body = text[end + 4:].lstrip("\n")
    meta: dict[str, str] = {}
    for line in block.splitlines():
        if ":" in line:
            key, _, val = line.partition(":")
            meta[key.strip()] = val.strip()
    return meta, body


def _stanzas(body: str) -> list[list[str]]:
    stanzas: list[list[str]] = []
    for chunk in body.replace("\r\n", "\n").strip("\n").split("\n\n"):
        lines = [ln.rstrip() for ln in chunk.split("\n") if ln.strip() != ""]
        if lines:
            stanzas.append(lines)
    return stanzas


def parse_markdown(text: str, source: str = "") -> Poem:
    meta, body = _parse_frontmatter(text)
    title = meta.get("title", "")
    if not title and body.startswith("# "):
        first, _, rest = body.partition("\n")
        title = first[2:].strip()
        body = rest.lstrip("\n")
    stanzas = _stanzas(body)
    first_line = stanzas[0][0] if stanzas and stanzas[0] else ""
    if is_index_title(title, first_line):  # don't render an index-convention title
        title = ""
    return Poem(
        title=title,
        author=meta.get("author", ""),
        stanzas=stanzas,
        source=source,
        meta=meta,
    )


def load_file(path: str | Path) -> Poem:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(text)
        body = data.get("body", "")
        stanzas = data["stanzas"] if "stanzas" in data else _stanzas(body)
        return Poem(
            title=data.get("title", ""),
            author=data.get("author", ""),
            stanzas=stanzas,
            source=str(path),
            meta={k: v for k, v in data.items() if k not in {"title", "author", "stanzas", "body"}},
        )
    return parse_markdown(text, source=str(path))


class LocalSource:
    """Folder-backed Source. Pass an explicit `poem` to pin one file, else a poem
    is chosen deterministically per day so the frame is stable within a day."""

    def __init__(self, directory: str | Path, poem: str | Path | None = None):
        self.directory = Path(directory)
        self.poem = Path(poem) if poem else None

    def poem_for(self, day: date) -> Poem:
        if self.poem:
            return load_file(self.poem)
        candidates = sorted(p for p in self.directory.glob("*") if p.suffix in {".md", ".json"})
        if not candidates:
            raise FileNotFoundError(f"No .md/.json poems in {self.directory}")
        idx = daily_pick([str(p) for p in candidates], day)  # shuffled deck, one per day
        return load_file(candidates[idx])
