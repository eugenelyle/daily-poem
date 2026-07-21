# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

An e-ink poetry frame. A Raspberry Pi 4 typesets one poem a day and pushes it to a Pimoroni Inky Impression 7.3" (Spectra 6) panel. Development happens on a Mac (renders a preview PNG); deployment on the Pi (pushes to the panel). One flag — `DAILY_POEM_TARGET=preview|inky` — switches between them. The project is **deployed and live**; changes should keep the Pi path working.

## Commands

```bash
# Setup (Mac dev — Pillow etc. only; the inky driver is Pi-only and won't build on macOS)
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

# Render today's poem -> out/preview.png
./.venv/bin/python -m daily_poem render
./.venv/bin/python -m daily_poem render --poem poems/sample.md   # specific local file
./.venv/bin/python -m daily_poem render --date 2026-07-01        # pick by date

# Companion (page 2) pipeline — needs ANTHROPIC_API_KEY (env or .env at repo root)
./.venv/bin/python -m daily_poem companion --poem poems/sample.md --dry-run
./.venv/bin/python -m daily_poem show-companion --target preview  # compose saved companion

# Button server (flips the panel between poem and companion)
./.venv/bin/python -m daily_poem serve --port 8099

# Tests — plain asserts, no framework; run the file directly
./.venv/bin/python tests/test_notion_parse.py

# Regenerate the panel palette after bumping the inky version
./.venv/bin/python scripts/extract_palette.py
```

There is no linter or build step. On the Pi, install `requirements-pi.txt` instead (pulls `inky>=2.4.0` — the version pin matters because `palette.json` is extracted from it).

## Architecture

Four decoupled layers, each seam a small protocol (not a class hierarchy). Data flows `content → render → device`, with `companion` as a parallel pipeline:

- **`daily_poem/content/`** — produces a `Poem` (`content/base.py`). Backends: `local.py` (Markdown/JSON files in `poems/`, deterministic pick per date) and `notion.py` (live Notion database, filtered by `status_in`). `make_source(cfg)` chooses by `source.backend`. The Notion body parser handles two storage styles (line-per-paragraph and stanza-per-paragraph), suppresses "index titles" (title equal to the first line), and stops at the first `---` divider (bilingual poems render the original only). This parser is what `tests/test_notion_parse.py` covers.
- **`daily_poem/render/`** — typesets the `Poem` into a panel-ready `'P'`-mode image quantized to the 6 inks. `layout.py` auto-fits the largest body size where the longest line fits the width and the whole poem fits the height (never re-wraps the poet's lines); `compose.py` has two entry points: `compose()` for page 1 (poem, mono dither) and `compose_companion()` for page 2 (full-colour dither). `palette.py`/`palette.json` mirror the inky library's quantization (saturated/desaturated blend + Floyd–Steinberg) so the Mac preview matches hardware dithering.
- **`daily_poem/device/`** — transport only: `preview.py` saves a PNG, `inky_push.py` pushes to the panel (imports `inky` lazily; rotates by `page.rotate_for_panel` first).
- **`daily_poem/companion/`** — the "page 2" pipeline: `distill → gather → rank+lens → gate → emit` (`run_pipeline` in `__init__.py`). Distill/rank call the Anthropic API using prompts in `prompts/`; gather pulls candidates from public sources (PoetryDB, Wikipedia, museums…); the gate rejects images that would dither to mud. Output is only `out/companion.{png,json}` — it never touches the panel. `server.py` is a stdlib HTTP button server (`/health`, `/companion`, `/poem`, `/toggle`) that shells out to `python -m daily_poem ...` per press so a render crash can't kill it; a lock serializes pushes (second press mid-refresh → 409). The editorial reasoning behind the pipeline is in `companion-discovery-handoff.md`.

`daily_poem/__main__.py` is the CLI (`render`, `companion`, `show-companion`, `serve`). `out/current_page` records which page is showing; `/toggle` reads it to flip.

## Configuration

`config.toml` is **the single knob file** — fonts, margins, leading, auto-fit bounds, palette, source, companion settings all live there, loaded into frozen dataclasses by `daily_poem/config.py`. When adding a tunable, add it to both the TOML and the matching dataclass. Env overrides keep the committed config machine-agnostic: `DAILY_POEM_TARGET`, `DAILY_POEM_BACKEND`, `DAILY_POEM_NOTION_DATABASE_ID`. Secrets (`NOTION_TOKEN`, `ANTHROPIC_API_KEY`) come from the environment or a root `.env` — never from config or git.

## Conventions and constraints

- Poem line breaks are sacred: the renderer auto-fits type size (and tightens leading down to `line_height_min`) rather than ever re-wrapping lines.
- The page is composed portrait 480×800; the panel is physically 800×480 landscape — `rotate_for_panel = 270` is applied only at push time and was tuned on real hardware. Don't "fix" the apparent mismatch.
- Keep `inky` out of `requirements.txt` and out of module-level imports on shared code paths — it must stay importable on macOS.
- The poem dithers against black+white only (`palette.mode = "mono"`) for crisp serifs; `"full"` is reserved for companion art.
- Deployment is systemd on the Pi (`systemd/`): `daily-poem.timer` fires at 01:00 → `daily-poem.service` renders → `Wants=`/`After=` chains `daily-companion.service`, so the companion is always paired to that day's poem (the companion has no timer of its own). `daily-companion-server.service` runs the button server at boot.
- The button server has no auth by design — LAN only.
- A failed or empty companion run is deliberately harmless: the poem is unaffected; a blank companion just means no second page that day. Preserve this failure isolation.
