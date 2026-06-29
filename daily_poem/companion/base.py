"""The companion interface — the seam the editorial 'brain' drops into later.

A Companion takes the poem in and optionally returns a deepening pairing
(text / image / fact) to render alongside it. Today the only implementation is
a no-op; the real LLM logic is developed separately and slots in here without
touching content/, render/, or device/.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol

from ..content.base import Poem


@dataclass(frozen=True)
class Companion:
    kind: str                  # "text" | "image" | "fact" | ...
    text: str = ""
    image_path: str = ""
    meta: dict | None = None


class CompanionSource(Protocol):
    def companion_for(self, poem: Poem) -> Optional[Companion]: ...
