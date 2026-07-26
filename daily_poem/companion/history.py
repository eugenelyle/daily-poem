"""A short memory of what has already been shown.

The pipeline is otherwise stateless: out/companion.json is overwritten each
night, so nothing stopped the same companion arriving again a few days later.
(The Apophatic theology article landed three times in a fortnight.)

This keeps a rolling list of the last `history_size` companions and excludes
them from the candidate pool before ranking — before, so the model doesn't
spend a lens on something that can't be chosen.

Deliberately narrow: it remembers *companions*, not poems. Repeats of a poem
finding a different companion are a feature (see the handoff doc, §4).
"""
from __future__ import annotations

import json
import logging
from datetime import date

from ..config import Config

log = logging.getLogger(__name__)


def _path(cfg: Config):
    return cfg.path(cfg.companion.history_path)


def load(cfg: Config) -> list[dict]:
    """Read the history file; a missing or corrupt file is an empty history."""
    path = _path(cfg)
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        log.warning("companion history unreadable (%s); treating as empty", exc)
        return []


def recent_keys(cfg: Config) -> set[str]:
    """The URLs shown recently — the exclusion set."""
    return {e["key"] for e in load(cfg) if e.get("key")}


def key_for(url: str, candidate_id: str = "") -> str:
    """Identity of a companion. The source URL is stable across runs; the
    candidate id is a hash of fetch-time metadata, so it's only a fallback."""
    return url.strip() or candidate_id


def exclude_recent(candidates: list, cfg: Config) -> list:
    """Drop candidates shown within the history window."""
    if not cfg.companion.history_size:
        return candidates
    seen = recent_keys(cfg)
    if not seen:
        return candidates
    kept = [c for c in candidates if key_for(c.url, c.id) not in seen]
    dropped = len(candidates) - len(kept)
    if dropped:
        log.info("excluded %d candidate(s) shown in the last %d companions",
                 dropped, cfg.companion.history_size)
    return kept


def record(cfg: Config, payload: dict, *, today: date | None = None) -> None:
    """Append today's companion and trim to the window. Best-effort — a history
    write must never fail the night's run."""
    if payload.get("type") not in ("text", "image"):
        return  # a blank day shows nothing, so it bars nothing later
    key = key_for(payload.get("url", ""))
    if not key:
        return
    try:
        entries = [e for e in load(cfg) if e.get("key") != key]
        entries.append({
            "date": (today or date.today()).isoformat(),
            "key": key,
            "source_name": payload.get("source_name", ""),
            "attribution": payload.get("attribution", ""),
        })
        entries = entries[-cfg.companion.history_size:]
        path = _path(cfg)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(entries, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    except OSError as exc:
        log.warning("could not write companion history: %s", exc)
