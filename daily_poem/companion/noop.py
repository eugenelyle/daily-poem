"""No-op companion. Returns nothing; the poem stands alone."""
from __future__ import annotations

from typing import Optional

from ..content.base import Poem
from .base import Companion


class NoopCompanion:
    def companion_for(self, poem: Poem) -> Optional[Companion]:
        return None
