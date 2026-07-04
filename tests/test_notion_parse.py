"""Parser tests for the Notion source, against the Notion block shape.

Run: ./.venv/bin/python tests/test_notion_parse.py
(Plain asserts — no test-framework dependency. Fixture verse is invented.)
"""
from __future__ import annotations

from daily_poem.content.notion import blocks_to_stanzas, page_to_poem


def _para(text: str) -> dict:
    rich = [] if text == "" else [{"plain_text": text}]
    return {"type": "paragraph", "paragraph": {"rich_text": rich}}


# One storage style: each line is its own paragraph; an empty paragraph is a
# stanza break. (This is the block JSON the REST API returns.) Shape: [6, 6, 1, 4].
LINES = [
    "the morning light arrives", "across the open field",
    "a heron lifts and turns", "above the silver stream",
    "the day unfolds in grey", "and slowly finds its blue", "",
    "here the second stanza", "gathers up its weight",
    "each line a measured step", "across the open page",
    "toward some kind of meaning", "waiting at the edge", "",
    "one line standing alone", "",
    "and then the close arrives", "holding what came before",
    "the small and ordinary", "made to seem enough",
]
BLOCKS = [_para(t) for t in LINES]


def test_stanza_structure():
    stanzas = blocks_to_stanzas(BLOCKS)
    assert [len(s) for s in stanzas] == [6, 6, 1, 4], [len(s) for s in stanzas]
    assert stanzas[0][0] == "the morning light arrives"
    assert stanzas[2] == ["one line standing alone"]


def test_ignores_non_paragraphs_and_trailing_blanks():
    blocks = [_para("only line"), {"type": "divider", "divider": {}}, _para("")]
    assert blocks_to_stanzas(blocks) == [["only line"]]


def test_soft_line_breaks_within_a_block():
    blocks = [_para("line one\nline two"), _para(""), _para("line three")]
    assert blocks_to_stanzas(blocks) == [["line one", "line two"], ["line three"]]


def test_style_b_consecutive_multiline_paragraphs():
    # Other storage style: each paragraph IS a stanza (lines via soft breaks),
    # with NO empty blocks between them.
    blocks = [_para("a\nb\nc"), _para("d\ne"), _para("f\ng\nh")]
    assert blocks_to_stanzas(blocks) == [["a", "b", "c"], ["d", "e"], ["f", "g", "h"]]


def test_divider_stops_parsing_original_only():
    # Bilingual poems: original, '---', then translation. We keep the original only.
    blocks = [
        _para("the first line here\nthe second line here"),
        {"type": "divider", "divider": {}},
        _para("[translation]"),
        _para("a translated line"),
    ]
    assert blocks_to_stanzas(blocks) == [["the first line here", "the second line here"]]


def test_genuine_title_is_kept():
    page = {"url": "u", "properties": {
        "Title": {"type": "title", "title": [{"plain_text": "A Quiet Field"}]},
        "First Line": {"type": "rich_text", "rich_text": []},
    }}
    poem = page_to_poem(page, [_para("the morning light\narrives across the field")])
    assert poem.title == "A Quiet Field"        # genuine title -> rendered
    assert poem.lines[0] == "the morning light"


def test_author_property_becomes_byline():
    # Another poet's poem: a genuine title AND an Author -> both available to render.
    page = {"url": "u", "properties": {
        "Title": {"type": "title", "title": [{"plain_text": "The Second Coming"}]},
        "Author": {"type": "rich_text", "rich_text": [{"plain_text": "W. B. Yeats"}]},
    }}
    poem = page_to_poem(page, [_para("Turning and turning in the widening gyre")])
    assert poem.title == "The Second Coming"
    assert poem.author == "W. B. Yeats"


def test_missing_author_is_empty_not_none():
    # My own poems have no Author property -> author is "" so no byline renders.
    page = {"url": "u", "properties": {
        "Title": {"type": "title", "title": [{"plain_text": "A Quiet Field"}]},
    }}
    poem = page_to_poem(page, [_para("the morning light")])
    assert poem.author == ""


def test_page_to_poem_keeps_metadata_not_title():
    page = {
        "url": "https://notion.so/x",
        "properties": {
            # Index-convention title == the first line -> must NOT render.
            "Title": {"type": "title", "title": [{"plain_text": "The morning light arrives"}]},
            "First Line": {"type": "rich_text", "rich_text": [{"plain_text": "the morning light arrives"}]},
            "Form": {"type": "select", "select": {"name": "Free Verse"}},
            "Themes": {"type": "multi_select", "multi_select": [{"name": "Nature"}, {"name": "Time"}]},
            "Line Count": {"type": "number", "number": 19},
            "Status": {"type": "select", "select": {"name": "Complete"}},
        },
    }
    poem = page_to_poem(page, BLOCKS)
    assert poem.title == ""                       # index title is suppressed
    assert poem.meta["form"] == "Free Verse"
    assert poem.meta["themes"] == ["Nature", "Time"]
    assert poem.meta["first_line"] == "the morning light arrives"
    assert poem.lines[0] == "the morning light arrives"


if __name__ == "__main__":
    n = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
            n += 1
    print(f"\n{n} passed")
