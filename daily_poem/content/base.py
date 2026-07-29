"""The Poem datatype and the Source interface.

A Source answers one question: "what poem for this day?" The local-export
source is the only implementation today; a Notion source drops in later by
satisfying the same shape — render/ and device/ never need to change.
"""
from __future__ import annotations

import hashlib
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


def daily_pick(keys: list[str], day: date) -> int:
    """Index of the day's poem, dealt from a shuffled deck.

    A shuffle bag, not an independent draw. The collection is shuffled into an
    order, walked one per day, and reshuffled when it runs out — so every poem
    appears exactly once per cycle and none can hide. A true random draw fails
    that badly at this size: with 226 poems it repeats within ~19 days on
    average while leaving ~45 of them unseen after a full year.

    Deterministic and stateless — the answer comes from the date alone, so the
    same day yields the same poem on any machine, with nothing to persist and
    nothing to lose when the Pi is rebuilt.

    The shuffle is seeded with the cycle number, giving a fresh order on each
    pass through the collection. It sorts on a hash rather than `random.seed()`
    because Python makes no promise that its RNG stream is stable across
    versions, and this ordering has to hold for years.

    `keys` are stable per-poem identities (Notion page ids, file paths) — NOT
    positions, or the order would shift whenever a poem is added. Sorting on the
    raw key is what produced months of one book at a time: Notion issues ids in
    creation order and the books were imported as blocks, so an id sort is a
    sort by book. Hashing breaks that correlation.
    """
    n = len(keys)
    if n == 0:
        raise ValueError("daily_pick needs at least one key")
    cycle, position = divmod(day.toordinal(), n)
    order = sorted(range(n),
                   key=lambda i: hashlib.md5(f"{cycle}:{keys[i]}".encode()).hexdigest())
    return order[position]


def is_index_title(title: str, first_line: str) -> bool:
    """True when `title` is just the index-convention first line (capitalized for
    sorting), so it should NOT be rendered. False for a genuine, distinct title.
    Empty titles count as index (nothing to render)."""
    t = (title or "").strip().casefold()
    return not t or t == (first_line or "").strip().casefold()
