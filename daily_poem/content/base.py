"""The Poem datatype and the Source interface.

A Source answers one question: "what poem for this day?" The local-export
source is the only implementation today; a Notion source drops in later by
satisfying the same shape — render/ and device/ never need to change.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class Poem:
    title: str
    author: str
    stanzas: list[list[str]]  # stanzas -> lines; the poet's line breaks are preserved verbatim
    source: str = ""          # provenance (file path, Notion id, ...)
    meta: dict = field(default_factory=dict)

    @property
    def lines(self) -> list[str]:
        return [line for stanza in self.stanzas for line in stanza]


class Source(Protocol):
    def poem_for(self, day: date) -> Poem: ...


def is_index_title(title: str, first_line: str) -> bool:
    """True when `title` is just the index-convention first line (capitalized for
    sorting), so it should NOT be rendered. False for a genuine, distinct title.
    Empty titles count as index (nothing to render)."""
    t = (title or "").strip().casefold()
    return not t or t == (first_line or "").strip().casefold()
