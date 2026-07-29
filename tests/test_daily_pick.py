"""Tests for the daily poem rotation — the shuffle bag in content/base.py.

Pins the two properties the frame depends on (the same day always yields the
same poem; a full cycle shows every poem exactly once) and the bug that
prompted it: sorting on raw Notion ids sorted by book, so the frame served
one book for months at a time.

Run: ./.venv/bin/python tests/test_daily_pick.py
(Plain asserts — no test-framework dependency.)
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from daily_poem.content.base import daily_pick

# Notion issues ids in creation order, so a book imported as a block shares a
# prefix. This mirrors the real collection: 99 Longings, then 121 Directions.
KEYS = ([f"2f196022-1f78-{i:04x}-longings" for i in range(99)] +
        [f"2f296022-1f78-{i:04x}-directions" for i in range(121)])
N = len(KEYS)          # 220, close enough to the real 226
START = date(2026, 7, 26)
# The deck is reshuffled when it runs out, so the exactly-once guarantee holds
# over a cycle measured from a reshuffle — not over any arbitrary N-day window.
ALIGNED = date.fromordinal((START.toordinal() // N + 1) * N)


def _book(key: str) -> str:
    return key.rsplit("-", 1)[1]


def _picks(days: int, start: date = START) -> list[int]:
    return [daily_pick(KEYS, start + timedelta(days=i)) for i in range(days)]


# --- the two properties the frame depends on ---------------------------------

def test_same_day_always_yields_the_same_poem():
    """Determinism: the render and the companion job run separately and must agree."""
    for day in (START, date(2026, 1, 1), date(2027, 3, 14)):
        assert len({daily_pick(KEYS, day) for _ in range(5)}) == 1


def test_a_full_cycle_shows_every_poem_exactly_once():
    counts = Counter(_picks(N, ALIGNED))
    assert len(counts) == N, f"only {len(counts)} of {N} poems appeared"
    assert set(counts.values()) == {1}


def test_no_poem_repeats_within_a_cycle():
    picks = _picks(N, ALIGNED)
    assert len(picks) == len(set(picks))


def test_a_window_straddling_a_reshuffle_may_double_up_and_skip():
    """Honest bound on the guarantee. Across a reshuffle the deck is dealt anew,
    so an arbitrary N-day window is not a permutation — a poem can fall late in
    one cycle and early in the next, while another waits.

    Measured coverage runs 75%-95%, worst at the exact midpoint straddle (tested
    here). Still well ahead of a true random draw, which covers only ~63% of the
    collection in the same span, and every poem is shown exactly once per
    aligned cycle regardless."""
    counts = Counter(_picks(N, ALIGNED - timedelta(days=N // 2)))
    assert len(counts) < N                       # not a clean permutation
    assert len(counts) > N * 0.70                # but nothing pathological
    assert max(counts.values()) == 2             # at worst twice, never more


# --- the bug this replaced ---------------------------------------------------

def test_consecutive_days_are_not_adjacent_in_source_order():
    """The old scheme walked the id-sorted list one step a day. If picks are
    still consecutive integers, the shuffle isn't happening."""
    picks = _picks(20)
    steps = [b - a for a, b in zip(picks, picks[1:])]
    assert steps.count(1) < 3, f"picks look sequential: {picks}"


def test_both_books_appear_within_a_fortnight():
    """The symptom: months of Directions with no Longings in sight."""
    books = {_book(KEYS[i]) for i in _picks(14)}
    assert books == {"longings", "directions"}, books


def test_book_mix_over_a_cycle_matches_the_corpus():
    """Exactly-once per cycle means the mix is the corpus mix, by construction."""
    books = Counter(_book(KEYS[i]) for i in _picks(N, ALIGNED))
    assert books["longings"] == 99
    assert books["directions"] == 121


# --- reshuffling -------------------------------------------------------------

def test_each_cycle_deals_a_different_order():
    first = _picks(N, ALIGNED)
    second = _picks(N, ALIGNED + timedelta(days=N))
    assert first != second
    assert sorted(first) == sorted(second)  # same deck, new order


def test_two_aligned_cycles_show_everything_twice():
    counts = Counter(_picks(2 * N, ALIGNED))
    assert set(counts.values()) == {2}


# --- identity, not position --------------------------------------------------

def test_order_keys_on_identity_so_reordering_the_input_is_harmless():
    """Sources sort their own lists; the pick must follow the poem, not the slot."""
    day = START
    chosen = KEYS[daily_pick(KEYS, day)]
    shuffled = list(reversed(KEYS))
    assert shuffled[daily_pick(shuffled, day)] == chosen


def test_single_poem_collection_works():
    assert daily_pick(["only"], START) == 0


def test_empty_collection_is_an_error_not_a_crash_later():
    try:
        daily_pick([], START)
    except ValueError:
        return
    raise AssertionError("expected ValueError for an empty collection")


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            n += 1
    print(f"\n{n} passed")
