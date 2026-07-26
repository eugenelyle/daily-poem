"""Tests for the companion pipeline's pure logic — angle parsing, the Wiktionary
etymology cut, index-article filtering, and the repeat-exclusion history.

The network fetchers themselves aren't covered here (they need live APIs); what
is covered is the logic that silently starved the pool: sentence-length queries
and an empty extract that no test would have caught.

Run: ./.venv/bin/python tests/test_companion_sources.py
(Plain asserts — no test-framework dependency.)
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import replace
from datetime import date
from pathlib import Path

from daily_poem import config as config_mod
from daily_poem.companion import history
from daily_poem.companion.distill import Angle, parse_angles
from daily_poem.companion.gather import Candidate, _is_index_article, extract_etymology


# --- angle parsing -----------------------------------------------------------

def test_angle_keeps_term_and_prose_separate():
    angles = parse_angles([{"term": "kenosis", "angle": "the emptying that makes room"}])
    assert angles == [Angle(term="kenosis", prose="the emptying that makes room")]


def test_quoted_and_punctuated_terms_are_cleaned():
    # A term arriving as "'brilliant'" or "kenosis:" must not reach the APIs
    # with its punctuation — that is what killed the Wiktionary lookups.
    assert parse_angles([{"term": "'brilliant'", "angle": "x"}])[0].term == "brilliant"
    assert parse_angles([{"term": "kenosis:", "angle": "x"}])[0].term == "kenosis"


def test_bare_string_angle_salvages_a_short_term():
    """The old prose-only shape must still yield something searchable."""
    angles = parse_angles(["kenosis: the theological emptying of self as precondition"])
    assert angles[0].term == "kenosis"
    assert angles[0].prose.startswith("kenosis:")


def test_missing_term_falls_back_to_the_prose_head():
    angles = parse_angles([{"angle": "threshold — the crossing worn by feet"}])
    assert angles[0].term == "threshold"


def test_termless_junk_is_dropped_not_queried():
    assert parse_angles([{"term": "", "angle": ""}, {"term": "  ", "angle": ""}]) == []


# --- Wiktionary etymology ----------------------------------------------------

WIKTIONARY_EXTRACT = """== English ==

=== Etymology ===
From New Latin nostalgia, coined by Johannes Hofer in 1688 from Ancient Greek
νόστος (nóstos, "returning home") + ἄλγος (álgos, "pain").

=== Pronunciation ===
IPA: /nɒsˈtaldʒə/
"""


def test_etymology_section_is_extracted():
    etym = extract_etymology(WIKTIONARY_EXTRACT)
    assert etym.startswith("From New Latin nostalgia")
    assert "returning home" in etym
    assert "IPA" not in etym  # must stop at the next heading


def test_numbered_etymology_heading_is_found():
    """Words with several senses use 'Etymology 1' — e.g. 'want'."""
    extract = "== English ==\n\n=== Etymology 1 ===\nFrom Middle English wanten, to lack.\n\n=== Noun ===\n"
    assert extract_etymology(extract).startswith("From Middle English wanten")


def test_entry_without_etymology_returns_empty():
    assert extract_etymology("== English ==\n\n=== Noun ===\nA thing.\n") == ""


def test_etymology_is_truncated():
    long_extract = "=== Etymology ===\n" + ("word " * 400)
    assert len(extract_etymology(long_extract, max_chars=600)) == 600


# --- index articles ----------------------------------------------------------

def test_wikipedia_index_pages_are_rejected():
    # 'List of Latin phrases (full)' was a real companion candidate.
    for title in ["List of Latin phrases (full)", "Glossary of art terms",
                  "Outline of philosophy", "Mercury (disambiguation)"]:
        assert _is_index_article(title), title


def test_real_articles_survive():
    for title in ["Apophatic theology", "Kenosis", "Différance", "Simone Weil"]:
        assert not _is_index_article(title), title


# --- repeat exclusion --------------------------------------------------------

def _cfg(tmp: Path, history_size: int = 30):
    cfg = config_mod.load(Path(__file__).resolve().parent.parent / "config.toml")
    companion = replace(cfg.companion,
                        history_path=str(tmp / "history.json"),
                        history_size=history_size)
    return config_mod.Config(**{**cfg.__dict__, "root": tmp, "companion": companion})


def _cand(url: str, cid: str = "abc") -> Candidate:
    return Candidate(id=cid, type="text", content_or_description="…",
                     source_name="Wikipedia", attribution="Wikipedia: x", url=url)


APOPHATIC = "https://en.wikipedia.org/wiki/Apophatic_theology"


def test_recently_shown_companion_is_excluded():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg(Path(d))
        history.record(cfg, {"type": "text", "url": APOPHATIC,
                             "source_name": "Wikipedia", "attribution": "Wikipedia: Apophatic theology"})
        pool = [_cand(APOPHATIC), _cand("https://en.wikipedia.org/wiki/Kenosis", "def")]
        kept = history.exclude_recent(pool, cfg)
        assert [c.url for c in kept] == ["https://en.wikipedia.org/wiki/Kenosis"]


def test_history_window_is_trimmed_and_old_entries_expire():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg(Path(d), history_size=3)
        for i in range(5):
            history.record(cfg, {"type": "text", "url": f"https://example.org/{i}"})
        entries = history.load(cfg)
        assert len(entries) == 3
        assert [e["key"] for e in entries] == [f"https://example.org/{i}" for i in (2, 3, 4)]
        # The oldest has aged out, so it may be shown again.
        assert history.exclude_recent([_cand("https://example.org/0")], cfg)


def test_recording_the_same_companion_twice_keeps_one_entry():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg(Path(d))
        history.record(cfg, {"type": "text", "url": APOPHATIC}, today=date(2026, 7, 20))
        history.record(cfg, {"type": "text", "url": APOPHATIC}, today=date(2026, 7, 25))
        entries = history.load(cfg)
        assert len(entries) == 1
        assert entries[0]["date"] == "2026-07-25"


def test_blank_day_records_nothing():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg(Path(d))
        history.record(cfg, {"type": "question", "buried_question": "…"})
        assert history.load(cfg) == []


def test_history_size_zero_disables_exclusion():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg(Path(d), history_size=0)
        pool = [_cand(APOPHATIC)]
        # Even with a stale file present, size 0 means the gate is off.
        Path(cfg.companion.history_path).write_text(json.dumps([{"key": APOPHATIC}]))
        assert history.exclude_recent(pool, cfg) == pool


def test_corrupt_history_is_survivable():
    with tempfile.TemporaryDirectory() as d:
        cfg = _cfg(Path(d))
        Path(cfg.companion.history_path).write_text("{not json")
        assert history.load(cfg) == []
        assert history.exclude_recent([_cand(APOPHATIC)], cfg)  # pool passes through


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            n += 1
    print(f"\n{n} passed")
