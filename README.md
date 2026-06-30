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

The timer fires once a day at **01:00** and is the whole daily turnover: it renders
the poem, then (via `Wants=daily-companion.service`) selects the companion right
after, so the poem is always chosen first and the companion is paired to it. Install
the companion service too (next section) for that chain to fire. The unit assumes the
repo at `/home/pi/daily-poem` and user `pi`; edit it if you deploy elsewhere. e-ink
holds the last image with no power, so a missed run just means yesterday's poem lingers.

## The companion (page 2)

A second page — a found image or text, chosen by an LLM to *deepen* the day's
poem, with a one-line "lens" beneath it — is selected overnight and revealed on a
button press. The selection pipeline (`distill → gather → rank+lens → render gate
→ emit`) lives in `daily_poem/companion/`; the editorial reasoning behind it is in
`companion-discovery-handoff.md`.

Iterate on the Mac (runs the full pipeline against the live sources, no Pi needed):

```bash
export ANTHROPIC_API_KEY=sk-ant-...        # or put it in .env at the repo root
./.venv/bin/python -m daily_poem companion --poem poems/your-poem.md --dry-run
```

`--dry-run` prints the buried question, oblique angles, candidate pool, ranked
candidates with their lenses, and the render-gate outcome — without writing files.
Drop `--dry-run` to save `out/companion.png` + `out/companion.json`.

**Schedule it on the Pi.** The companion needs `ANTHROPIC_API_KEY` on top of the
`NOTION_TOKEN` the render already uses — append it to the same root-only env file:

```bash
umask 077; printf 'ANTHROPIC_API_KEY=%s\n' '<your-key>' >> /home/pi/daily-poem.env
```

The companion is **not on its own timer** — it's chained to the poem: `daily-poem.service`
pulls it in (`Wants=`) and it runs `After=` the render, so the poem is always selected
first and the companion is paired to that exact poem. Just install the service (no
enable needed — the 01:00 poem timer drives it):

```bash
sudo cp systemd/daily-companion.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start daily-companion.service     # one-off: prove the pipeline runs end-to-end
# (no enable/timer — daily-poem.timer triggers the poem, which pulls this in after it)
```

The companion job only *writes* `out/companion.{png,json}` — it never touches the
panel. A failed or empty run is harmless: the poem is unaffected, and a blank
companion simply means no second page that day.

### The button (page 2 on the panel)

Page 2 is revealed on demand by a small HTTP server. It flips the panel between the
poem and its companion:

```
GET  /health     -> {"status": "ok"}            connectivity check
POST /companion  -> push the day's companion (page 2) to the Inky
POST /poem       -> re-render today's poem (page 1) and push it
```

`/companion` just composes what the overnight job already chose (cheap, offline);
`/poem` returns the frame to the poem. A lock serializes pushes, so a second tap
mid-refresh gets a `409` instead of colliding on the panel. Try it on the Mac
(actions fail at the hardware push, which only exists on the Pi, but `--target
preview` exercises the compositing):

```bash
./.venv/bin/python -m daily_poem show-companion --target preview   # -> out/companion-page2.png
./.venv/bin/python -m daily_poem serve --port 8099                 # then curl http://127.0.0.1:8099/health
```

On the Pi, install it as a boot service (port and bind address are in `config.toml`
under `[companion]`):

```bash
sudo cp systemd/daily-companion-server.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now daily-companion-server.service
systemctl status daily-companion-server.service     # confirm it's listening on :8080
```

**iPhone Shortcut.** Create a Shortcut with one action — *Get Contents of URL* —
pointed at `http://<pi-host>:8080/companion`, method `POST`. Add it to the Home
Screen for a one-tap reveal; a second Shortcut to `/poem` returns to the poem. The
server has **no auth and is for the home network only** — don't forward the port
past your LAN.

## Status

**Deployed and live.** A Raspberry Pi 4 (Debian 13) renders a poem from the Notion
collection (filtered to Complete/Published) and pushes it to the Inky Impression
7.3" once a day at 01:00 via a systemd timer, then selects that poem's companion in
the same chained run.

- `content (local + notion) → render → device (preview | inky)` — the full chain
  runs on hardware; orientation (`rotate_for_panel=270`) and contrast (mono dither
  vs. pure black/white, `body_weight=480`) were tuned on the real panel.
- Notion source is live; the token lives in a root-only env file on the Pi, never
  committed. Deploy updates with `git pull` on the Pi (read-only deploy key).
- **Companion (page 2) — built end-to-end; awaiting hardware tuning.** The
  `distill → gather → rank+lens → render gate → emit` chain runs and an overnight
  timer (01:00) selects the day's companion; the button server pushes page 2 to the
  panel on an iPhone-Shortcut tap. The full chain is verified on the Mac (page 2
  composites correctly; the server dispatches; only the Pi-only Inky push is
  untested off-hardware). Remaining: tune the image render gate against real
  dithered output on the panel. See `companion-discovery-handoff.md` §9b.
