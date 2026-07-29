"""Notion-backed poem source — the production content path.

Maps the "Poetry Collection" database to Poems:
  - The poem TEXT is the page body: each line is a paragraph block; an empty
    paragraph is a stanza break. (Soft line breaks inside a paragraph are kept.)
  - `Title` is the capitalized first line for indexing — NOT rendered. A genuine,
    distinct title (e.g. another poet's "The Second Coming") IS rendered.
  - `Author` is the byline: blank for my own poems (no attribution line), a poet's
    name for others. Rendered only when set (and when `show_author` is on).
  - We keep the rich properties (Form, Themes, Line Count, Status, Book, ...) in
    Poem.meta so the editorial/companion layer can use them later.

Auth is an internal-integration token via the NOTION_TOKEN env var (never config).
Built on stdlib urllib so the Notion path adds no dependencies.

NOTE: the body parser is unit-tested (tests/test_notion_parse.py) against the real
data shape, but the live HTTP path needs a token to exercise end-to-end — see the
README "Sourcing from Notion" for the one-time integration setup.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import date

from .base import Poem, daily_pick, is_index_title

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


# --- property + body parsing (pure, testable) --------------------------------

def _plain(rich: list[dict]) -> str:
    return "".join(seg.get("plain_text", "") for seg in rich or [])


def blocks_to_stanzas(blocks: list[dict]) -> list[list[str]]:
    """Paragraph blocks -> stanzas, handling both storage styles in the collection:

      Style A: one line per paragraph, an empty paragraph marks a stanza break.
      Style B: one stanza per paragraph, lines split by soft breaks ("\\n").

    A multi-line paragraph is taken as a self-contained stanza (Style B); runs of
    single-line paragraphs accumulate into one stanza, flushed by empty paragraphs
    (Style A). Non-text blocks are ignored.

    Parsing STOPS at the first "---" divider: bilingual poems store the original,
    a divider, then an English translation — we render the original only.
    """
    stanzas: list[list[str]] = []
    cur: list[str] = []

    def flush():
        nonlocal cur
        if cur:
            stanzas.append(cur)
            cur = []

    for b in blocks:
        btype = b.get("type")
        if btype == "divider":
            flush()
            break  # original only: ignore a translation/appendix after the first '---'
        if btype != "paragraph":
            continue  # ignore images/headings/etc. for now
        text = _plain(b.get("paragraph", {}).get("rich_text", []))
        if text.strip() == "":
            flush()
            continue
        if "\n" in text:  # Style B: this paragraph is a whole stanza
            flush()
            stanzas.append([ln.rstrip() for ln in text.split("\n") if ln.strip() != ""])
        else:             # Style A: this paragraph is one line of the current stanza
            cur.append(text.rstrip())
    flush()
    return stanzas


def _prop(props: dict, name: str):
    """Best-effort scalar extraction across Notion property types."""
    p = props.get(name)
    if not p:
        return None
    kind = p.get("type")
    if kind in ("title", "rich_text"):
        return _plain(p[kind]) or None
    if kind in ("select", "status"):
        return (p[kind] or {}).get("name")
    if kind == "multi_select":
        return [o["name"] for o in p[kind]]
    if kind == "number":
        return p[kind]
    if kind == "date":
        return (p[kind] or {}).get("start")
    return None


def page_to_poem(page: dict, blocks: list[dict]) -> Poem:
    props = page.get("properties", {})
    notion_title = _prop(props, "Title") or ""
    stanzas = blocks_to_stanzas(blocks)
    first_line = stanzas[0][0] if stanzas and stanzas[0] else ""
    # Render a title only when it's a genuine, distinct title (e.g. "Distant
    # Friends") — not the index-convention capitalized first line.
    title = "" if is_index_title(notion_title, first_line) else notion_title
    meta = {
        "first_line": _prop(props, "First Line"),
        "form": _prop(props, "Form"),
        "themes": _prop(props, "Themes"),
        "line_count": _prop(props, "Line Count"),
        "status": _prop(props, "Status"),
        "book": _prop(props, "Book"),
        "date_written": _prop(props, "Date Written"),
        "notion_title": notion_title or None,
    }
    return Poem(
        title=title,
        author=_prop(props, "Author") or "",  # blank for my own poems; a poet's name for others
        stanzas=stanzas,
        source=page.get("url", page.get("id", "")),
        meta={k: v for k, v in meta.items() if v is not None},
    )


# --- live source -------------------------------------------------------------

class NotionSource:
    def __init__(self, token: str, database_id: str, status_in: list[str] | None = None):
        if not token:
            raise ValueError("NOTION_TOKEN is required for the Notion source")
        self.token = token
        self.database_id = database_id
        self.status_in = set(status_in) if status_in else None

    def _request(self, method: str, path: str, body: dict | None = None) -> dict:
        req = urllib.request.Request(
            f"{API}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Notion-Version": NOTION_VERSION,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:400]
            raise RuntimeError(f"Notion API {e.code} on {method} {path}: {detail}") from None

    def _paginate(self, method: str, path: str, body: dict | None = None) -> list[dict]:
        results: list[dict] = []
        cursor = None
        while True:
            payload = dict(body or {})
            if method == "POST" and cursor:
                payload["start_cursor"] = cursor
            req_path = path
            if method == "GET" and cursor:
                req_path = f"{path}{'&' if '?' in path else '?'}start_cursor={cursor}"
            data = self._request(method, req_path, payload if method == "POST" else None)
            results.extend(data.get("results", []))
            if not data.get("has_more"):
                return results
            cursor = data.get("next_cursor")

    def _eligible_pages(self) -> list[dict]:
        pages = self._paginate("POST", f"/databases/{self.database_id}/query", {"page_size": 100})
        if self.status_in:
            pages = [p for p in pages if _prop(p.get("properties", {}), "Status") in self.status_in]
        # Stable order so the daily pick doesn't depend on API ordering. This is
        # only a canonical baseline — `daily_pick` does the shuffling, and must,
        # because Notion ids sort by creation order and therefore by book.
        pages.sort(key=lambda p: p.get("id", ""))
        return pages

    def poem_for(self, day: date) -> Poem:
        pages = self._eligible_pages()
        if not pages:
            raise LookupError("No eligible poems in the Notion database")
        page = pages[daily_pick([p.get("id", "") for p in pages], day)]
        blocks = self._paginate("GET", f"/blocks/{page['id']}/children?page_size=100")
        return page_to_poem(page, blocks)
