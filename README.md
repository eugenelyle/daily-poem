# Daily Poem

An e-ink frame that shows one of my poems each day. A Raspberry Pi 4 renders a
typeset page once a day and pushes it to a **Pimoroni Inky Impression 7.3" 2025
(Spectra 6)** panel. Develop on a Mac (saves a preview PNG); deploy on the Pi
(pushes to the panel). One flag switches between them.

## Architecture

```
content/    pick the poem of the day (local .md/.json export; Notion drops in later)
render/     typeset it and quantize to the panel's 6 inks   ← the care goes here
device/     save a preview PNG (Mac)  OR  push to the Inky (Pi)   ← one flag
companion/  STUB: poem in -> optional deepening out. No-op today; the editorial
            "brain" lands here later without touching the rest.
config.toml the single knob file: fonts, margins, palette, source, flags
```

The layers are decoupled: `content` produces a `Poem`, `render` turns it into a
panel-ready image, `device` transports it. Each seam is one small protocol, not a
class hierarchy.

## Quick start (Mac)

```bash
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt        # Pillow only; inky is NOT installed here
./.venv/bin/python -m daily_poem render            # -> out/preview.png
```

Useful overrides while iterating:

```bash
./.venv/bin/python -m daily_poem render --poem poems/your-poem.md
./.venv/bin/python -m daily_poem render --date 2026-07-01
```

## Adding poems

Drop Markdown files in `poems/`:

```markdown
---
title: Stopping by Woods on a Snowy Evening
author: Robert Frost
---

Whose woods these are I think I know.
His house is in the village though;
...
```

- Optional `---` frontmatter (`title:`, `author:`). Without a `title:`, a leading
  `# Heading` is used.
- **Line breaks are preserved verbatim** — blank lines separate stanzas. The
  renderer never re-wraps your lines; it auto-fits the type so they fit.
- `.json` (`{"title","author","body"}` or `{"stanzas": [[...]]}`) also works.

Pin one poem with `source.poem` in `config.toml`, or leave it empty to rotate
through `poems/` deterministically by date.

## Sourcing from Notion

The production source reads your poem database directly. The poem text is the page
body (one paragraph per line; an empty paragraph is a stanza break); the capitalized
`Title` property is an index label and is **not** rendered.
Rich properties (`Form`, `Themes`, `Line Count`, `Status`, `Book`) are carried into
`Poem.meta` for the future companion layer.

One-time setup (yours to do — needs your login):

1. Create an internal integration at <https://www.notion.so/my-integrations>, copy
   its token.
2. Open your poem database → **⋯ → Connections → Connect to** your integration
   (this grants read access).
3. Switch the backend and provide the token (token via env, never committed):

   ```bash
   # config.toml
   [source]
   backend = "notion"

   # then
   export NOTION_TOKEN=secret_xxx
   ./.venv/bin/python -m daily_poem render
   ```

`status_in` in `config.toml` controls which poems are eligible for the daily
rotation (default: `["Complete", "Published"]`). The pick is deterministic per day.
The body parser is unit-tested (`tests/test_notion_parse.py`); the live HTTP path
is exercised once you add the token.

`--poem path.md` always reads a local file regardless of backend — handy for
iterating on a single poem.

**Data-shape handling.** The collection isn't uniform, so the body parser handles
both storage styles in it — one line per paragraph (empty-block stanza breaks) and
one stanza per paragraph (soft-break lines). Titles are auto-classified: a genuine
title (one distinct from the first line) renders; an index title equal to the first
line is suppressed. Accented/Unicode text renders (Literata covers it).

**Bilingual poems** store the original, a `---` divider, then a translation. The
parser **stops at the first `---`**, rendering the original language only.

**Not yet handled:** inline formatting — italic runs inside a line are flattened to
plain text (a future refinement).

## Typography & the palette

`render/` auto-fits the largest body size at which the longest line fits the
width and the whole poem fits the height; title and attribution scale with it.
Tune everything (font, weights, margins, leading, alignment, floor/ceiling sizes)
in `config.toml`.

The panel palette is **sourced from the `inky` library**, not hardcoded:
`daily_poem/render/palette.json` is extracted from `inky_e673.py`. Regenerate it
if you bump `inky`:

```bash
./.venv/bin/python scripts/extract_palette.py
```

Quantization mirrors the library (saturated/desaturated blend at `saturation`,
Floyd–Steinberg), so the preview matches hardware dithering. The poem is dithered
against **black + white only** (`palette.mode = "mono"`) for crisp serifs; switch
to `"full"` when the companion layer adds colour art. Note: at `saturation = 0.5`
the panel's "white" is a light grey — the preview shows that honestly; lower the
value for whiter paper.

> The preview is a close approximation, not a proof. Real Spectra-6 colour and
> dithering vary with panel batch and temperature — the first hardware render will
> still surprise us a little.

## Deploy on the Pi

**1. Enable the buses (once).** The Inky needs SPI and I2C:

```bash
sudo raspi-config nonint do_spi 0      # 0 = enable
sudo raspi-config nonint do_i2c 0
sudo apt update && sudo apt install -y python3-venv libopenjp2-7   # Pillow runtime dep
sudo reboot
```

**2. Get the code + deps:**

```bash
cd ~ && git clone https://github.com/eugenelyle/daily-poem.git   # or: git -C ~/daily-poem pull
cd ~/daily-poem
python3 -m venv .venv
./.venv/bin/pip install -r requirements-pi.txt    # pulls inky 2.4+ (gpiod/spidev) — Pi only
```

**3. First push — and validate it.** Push a known local poem:

```bash
DAILY_POEM_TARGET=inky ./.venv/bin/python -m daily_poem render --poem poems/there-is-a-time-of-wanting.md
```

Then check, in order:

- **Detection** — no error means `inky.auto()` found the panel. (A `ValueError`/
  EEPROM error usually means SPI/I2C isn't enabled or the ribbon is seated wrong.)
- **Orientation** — if the poem is upside-down or mirrored, flip `page.rotate_for_panel`
  in `config.toml` (try `270`) and push again. This is the one value I couldn't
  determine without the hardware.
- **Paper & contrast** — Spectra-6 "white" is a warm grey. If it's too grey or too
  muddy, tune `palette.saturation` (lower → whiter/cleaner; higher → more vivid).
  Compare against `out/preview.png` from your Mac.

**4. Go live + schedule.** Set up the Notion integration (see "Sourcing from Notion"),
then drop the token on the Pi — never in git or the repo:

```bash
umask 077; printf 'NOTION_TOKEN=%s\n' '<your-token>' > /home/pi/daily-poem.env
```

The `daily-poem.service` unit already sets `DAILY_POEM_TARGET=inky` and
`DAILY_POEM_BACKEND=notion` and reads the token from that file. Install the timer:

```bash
sudo cp systemd/daily-poem.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start daily-poem.service        # one-off: prove the scheduled path works
sudo systemctl enable --now daily-poem.timer
systemctl list-timers daily-poem.timer         # confirm next run
```

The unit assumes the repo at `/home/pi/daily-poem` and user `pi`; edit it if
you deploy elsewhere. e-ink holds the last image with no power, so a missed run just
means yesterday's poem lingers.

## Status

**Deployed and live.** A Raspberry Pi 4 (Debian 13) renders a poem from the Notion
collection (filtered to Complete/Published) and pushes it to the Inky Impression
7.3" each morning at 06:00 via a systemd timer.

- `content (local + notion) → render → device (preview | inky)` — the full chain
  runs on hardware; orientation (`rotate_for_panel=270`) and contrast (mono dither
  vs. pure black/white, `body_weight=480`) were tuned on the real panel.
- Notion source is live; the token lives in a root-only env file on the Pi, never
  committed. Deploy updates with `git pull` on the Pi (read-only deploy key).
- companion is a no-op stub — the editorial layer drops into that seam next.
