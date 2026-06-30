# Daily Poem — Companion / Discovery Layer

**Claude Code handoff & design spec**

---

## 0. What this document is

The Daily Poem device shows one of my own poems on an e-ink panel each morning (page 1 — already built). This document specifies the **second page**: a *companion* — a found piece of text, a fact, or an image — chosen by an LLM to **deepen** the poem, revealed when I press a button, with a single one-line "lens" beneath it.

The repo already has a stubbed `companion/` module with a no-op and a defined interface (poem in → optional companion out). This is the spec for fleshing that out. It preserves the editorial reasoning from a long planning session; **read the "editorial heart" section as carefully as the architecture** — it's the part that makes this worth building, and it's easy to flatten into something mundane if the judgment isn't right.

---

## 1. The concept in one breath

Front page: the poem, typeset, holding the panel all day. Press a button: a second page answers it — a painting, a line from a dead poet, an etymology, an odd fact — something *found in the world* that throws a particular light back onto the poem. One sentence of curatorial prose sits beneath it. That sentence is the whole game.

---

## 2. The editorial heart (do not flatten this)

The default failure of any LLM asked to "find something related" is to reach for the **obvious echo** and to **affirm**. That produces mud: the poem and a companion that merely restates it, side by side, for 24 hours. The entire design exists to fight that.

**Deepen, don't echo.** A good epigraph never repeats the work — it stands slightly above it and throws light down, so the poem reads as part of something older or larger than the moment that made it. It shares the *wound*, not the *words*.

**The mechanism is the buried question.** Don't select on the poem's subject or nouns. First have the model name, in a single sentence, the *unspoken question or tension the poem is circling*. Then find the companion that answers, witnesses, or gives lineage to **that question** — ideally from a different voice, century, or form, so it arrives as *kin discovered at a distance* rather than the poem's own reflection handed back.

**Oblique, not similar; adjacent, not identical.** The companion should be close enough to feel like fate, far enough to make the reader tilt their head. It may deepen by *gently complicating*, not only by agreeing.

**Deepen with torque, not a nod.** The specific risk of "deepen" (vs. "swerve") is an echo chamber — a machine that quietly assures the poet his feelings are universal and profound. That curdles into the saccharine. Keep a little friction in the kinship.

**The lens.** One sentence beneath the pairing — the hinge that does the deepening. Not "both are about X." A sentence that *changes how the poem is re-read* in light of the companion. Spare, unsentimental, a little oblique. It should read as authored, not explained.

**A blank day beats a muddy one.** If nothing in the candidate pool genuinely deepens the poem, the engine returns null and the second page stays empty (or shows a quiet fallback — see §8). Forcing a weak pairing is worse than showing none.

**Worked example (for calibration).** A poem circling *the loss of an unlived life* should NOT be paired with Frost's "Road Not Taken" (the cliché echo) — it should be paired with something oblique like *pentimento* (the earlier painting ghosting back through a canvas as it ages) or *saudade* (longing toward an absent thing that may never have existed). Different form, no shared words, and it complicates rather than restates. That is the target register.

---

## 3. Either-or media + separation of judgment

A companion may be **text or image** — the engine is polymorphic and chooses whichever deepens best on a given morning.

Keep two kinds of judgment in **separate heads**:

- **Editorial judgment** (subjective, LLM): which candidates deepen the poem, and in what rank order. The LLM has no business reasoning about dithering.
- **Technical judgment** (deterministic, code): can an image actually render well on the panel? A quality filter has no business reasoning about resonance.

**Flow:** the LLM returns a *ranked list* of candidates (text and image intermixed). Code walks the list: a text candidate is accepted as-is; an image candidate is run through the render gate (§7) and accepted only if it survives, otherwise it falls through to the next best. Always end with something good, or with the blank day.

**Lens-per-candidate (important implementation detail).** The lens is bound to its specific candidate — a sentence written for a painting is useless for the line of poetry you fall back to. So the editorial prompt must write a lens for **every** ranked candidate in its single pass. Then whatever survives the render gate already has its matching lens, with no second LLM call.

---

## 4. Runtime & timing

The selection job runs **overnight (~1 AM)**, hours before I look at it. This is a gift: nothing has to be fast or cheap. There is ample time to pull fresh sources, actually render-test images, and fall back gracefully.

- **Repeats allowed.** The same poem may resurface months later and find a *different* companion — that re-discovery is a feature, not a bug. Do not dedupe poems or pin a poem to a fixed companion.
- **Dynamic, not pre-vetted.** We deliberately rejected a hand-curated static image corpus. The overnight window makes fresh, on-the-fly retrieval and render-testing feasible, and keeps the companion a genuine surprise.

---

## 5. Candidate gathering (the genuinely hard part)

This is the open design problem. Spend the care here.

**Search with what's underneath, not the poem's words.** Searching with the poem's own vocabulary returns the obvious (more sea, more sunsets). Instead, the model first distills the poem into its **buried question + a few deliberately oblique angles** ("what far-off thing does this secretly rhyme with?"), and *those* become the search terms. The model's job in this step is to imagine *where to look*.

**Sources (all open / public web — I keep no local library):**

- **Literary text:** Project Gutenberg (public-domain canon — poems and prose), PoetryDB (classic poems queryable by theme/author/line).
- **Facts & "small doors":** Wikipedia (concepts — *pentimento*, counterfactual grief), Wiktionary (etymologies — e.g. *want* = to lack; *nostalgia* = *nostos* "homecoming" + *algos* "pain").
- **Images:** open-access museum APIs — the Met (open API, no key), Art Institute of Chicago (open API), Rijksmuseum (free key), Cleveland Museum of Art (open). Search the **artwork descriptions / metadata** to match the oblique angles.

**Public domain is a feature, not just a constraint.** It can't reach modern copyrighted poets — which pushes companions toward the older, the canonical, the voice from another century. That is exactly the "kin discovered at a distance" feeling. The thing that keeps us legal also keeps us timeless.

**Why naive similarity search is the wrong tool.** The best companions share a *question*, not words — they often have almost nothing in common on the surface. Plain embedding/similarity search is precisely the worst at finding that; it would shove them far apart. So don't lean on vector similarity for selection. Let the **model do the reaching** (generate oblique search terms, concepts, poet names) and let the **collections keep it honest** (real returned results).

**The real skill is translation.** Turning one buried question into the specific words, names, and concepts each source can actually answer. Too literal → the obvious. Too clever → empty result sets. This is where iteration will live.

---

## 6. Image rendering constraints + layout

- **Panel:** Pimoroni Inky Impression 7.3" 2025 Edition (PIM773), 800×480, 6-colour Spectra 6. Pull the palette **from the `inky` library**, don't hardcode it, so previews match hardware.
- **What dithers well:** painterly work, woodcuts, prints, graphic art with limited palettes — gorgeous. **What turns to mud:** photographs, fine detail, soft gradients. Image selection/gating must account for the *medium*, not just the meaning.
- **Layout — two pages, never one.** Do not cram poem + companion onto one surface (that's the muddying problem at the layout level). Page 1 = poem (front, all day). Page 2 = companion, full-bleed, with the one-line lens beneath, revealed on button press.

---

## 7. Proposed module shape (wire into the existing `companion/` stub)

Keep the existing decoupling (`content` / `render` / `device` / `companion` / `scheduler`). Build `companion/` as a pipeline:

1. **distill** (LLM) — poem → buried question + N oblique search angles. (See prompt §9a.)
2. **gather** (retrieval) — query Gutenberg / PoetryDB / Wikipedia / Wiktionary / museum APIs using the angles; assemble a small mixed pool of candidates `{id, type: text|image, content_or_description, source, url}`.
3. **rank + lens** (LLM) — poem + candidate pool → buried question, ranked candidates, a lens for *each*, or null. (See prompt §9b.)
4. **render gate** (deterministic) — walk the ranked list; for image candidates, download → quantize to the Inky palette → quality-check (reject muddy results) → accept or fall through; text candidates accepted directly.
5. **emit** — chosen companion (text or image, already palette-quantized if image) + its lens, handed to the `render`/`device` layer as the second page. Null → empty-state fallback.

**Empty state (decide with me):** on null, the second page could stay blank, repeat the poem, or — an option worth considering — show the **buried question** alone (some mornings the most interesting thing is the poem handed back with its question named for the first time). Treat displaying the buried question as a *future option*, not required for v1.

**Config-driven:** sources enabled, model/provider, prompt file paths, palette source, Mac-preview-vs-Pi-push flag (consistent with the existing app's gating).

---

## 8. The prompts (load from versioned text files, not baked into code)

The editorial voice is **craft I will tune by reading language**, in a separate conversational thread — not in Claude Code. So load these from versioned `.txt`/`.md` files the code reads at runtime. Build the socket; the soul drops in and gets iterated separately.

### 9a. Distill prompt (sketch)

> You are a reader with a poet's ear. Given a poem, name in ONE sentence the unspoken question or tension it circles — past its images and nouns, what is it really asking or aching toward? Then give 3–5 oblique angles for finding a companion that would *deepen* it: concepts, single words worth their etymology, named poets or traditions, or kinds of image — each chosen to rhyme with the buried question, NOT to restate the poem's surface. Return JSON: `{ "buried_question": "...", "angles": ["...", ...] }`. No preamble.

### 9b. Rank + lens prompt (full)

```
SYSTEM:
You are a curator with a poet's ear — the kind of reader who keeps a
commonplace book, who can hold two unlike texts side by side and feel the
current between them. Your task is to deepen a poem by pairing it with one
companion, the way a well-chosen epigraph deepens the work beneath it.

You will be given one poem and a pool of candidate companions (poems, prose
fragments, lines, facts, etymologies, or image descriptions), each with an id,
a type, and a source. Do three things:

1. BURIED QUESTION. Read the poem past its surface — past its images and nouns
   — for the unspoken question or tension it circles. Name it in one sentence.

2. RANK. Order the candidates from most to least deepening. To DEEPEN is to
   cast a particular light onto the poem so it reads as part of something older
   or larger than the moment that made it.
   - Rank by shared underlying QUESTION, not shared subject. Do NOT reward
     candidates that echo the poem's imagery or restate its theme; that
     flatters it and adds nothing.
   - Prefer a different voice, century, or form, so the kinship feels
     discovered at a distance rather than the poem's reflection handed back.
   - The best pairing is oblique: close enough to feel like fate, far enough
     to make the reader tilt their head. A companion may deepen by gently
     COMPLICATING, not only by agreeing.
   - Never rank for reassurance. Penalize anything whose only effect is to tell
     the poet his feelings are universal or profound.
   - If NONE genuinely deepens the poem, return an empty ranking. A blank day
     is better than a muddy one.

3. LENS (one per ranked candidate). For EACH ranked candidate, write ONE
   sentence to sit beneath that pairing — the hinge that does the deepening.
   Not "both are about X." A sentence that changes how the poem is re-read in
   light of THAT companion. Spare, unsentimental, a little oblique. It should
   feel authored, not explained. (Each candidate needs its own lens, because a
   later technical step may discard the top pick and fall to the next.)

Return only JSON, no preamble or markdown:
{
  "buried_question": "...",
  "ranked": [
    { "id": "...", "type": "text|image", "source": "...", "lens": "..." }
  ]
}
(ranked may be empty.)

USER:
POEM:
{{title}}
{{poem_text}}

CANDIDATES:
{{ for each: id | type | source | text-or-image-description }}
```

---

## 9. Scope for this handoff

Build the `companion/` pipeline end-to-end (distill → gather → rank+lens → render gate → emit), wired into the existing stub interface, with the prompts loaded from external versioned files.

**Provide a Mac-testable dry run** before any hardware: one command that takes a sample poem, runs the full pipeline against the live sources, and prints the buried question, the ranked candidates with their lenses, the render-gate outcome for any images, the final chosen companion — and saves an 800×480 preview PNG of the second page (palette applied). No Pi required.

Keep to the existing project conventions: Python, lean deps, venv, config-driven, `git pull` deploy to the Pi. Lead with a plan and surface trade-offs before writing a pile of code; bias to restraint.

---

## 9b. Build status (Milestone 1 — June 2026)

**Pipeline built and running on Mac.** `python -m daily_poem companion --poem <p> [--dry-run]` runs distill → gather → rank+lens → gate → emit end-to-end and writes `out/companion.{png,json}`. Modules: `companion/{distill,gather,rank,gate,emit}.py` + `__init__.py` orchestrator; prompts in `prompts/{distill,rank}.md`; page-2 layout in `render/compose.py:compose_companion`. Deps added: `anthropic`, `requests`, `python-dotenv`. Keys in project-root `.env` (gitignored).

**The editorial layer is excellent.** Distill produces a real buried question + genuinely oblique angles; rank writes per-candidate lenses in the target register (the Bruegel *Harvesters* and David *Death of Socrates* lenses landed). This part is working as designed.

**Two known issues, deliberately deferred until we have real candidates to calibrate against:**

1. **The render gate's mud detector is wrong.** It currently rejects only black+white-dominant (washed-out) images. The actual failure mode is the *opposite*: dark oil paintings (e.g. David's *Death of Socrates*) dither into noisy mud across all six inks and pass the gate looking unusable. Rework needed: judge tonal range + post-quantization contrast, reject low-key/low-contrast results. Calibrate the threshold against a batch of real, eyeballed candidates — not in the abstract.

2. **Candidate pool is thin and image-only in practice.** Typical run returns ~6 candidates, all from the Met + AIC; PoetryDB / Wikipedia / Wiktionary / Rijksmuseum frequently return 0 because the oblique angles are too abstract to match literal search. This is the spec's "real skill is translation" problem (§5). Likely fix: have distill emit *searchable* terms alongside the poetic angles, and bias image queries toward prints/woodcuts (which dither cleanly) over oil paintings.

**Milestone 2 — DONE.** `systemd/daily-companion.{service,timer}` run the pipeline at 01:00 and write `out/companion.{png,json}`. Needs `ANTHROPIC_API_KEY` appended to `/home/pi/daily-poem.env`. README documents the Pi install.

**Milestone 3 — DONE and DEPLOYED (hardware-verified 2026-06-29).** `companion/server.py` is a stdlib HTTP button server: `GET /health`, `POST /companion` (compose saved page 2 → push), `POST /poem` (re-render poem → push). Pushes serialized by a lock (409 if busy); each action shells out to the CLI (`show-companion` / `render`) so the long-lived server holds no Inky handle. New CLI commands: `show-companion` (compose the saved companion as page 2, preview or push) and `serve`. `systemd/daily-companion-server.service` runs it on boot. iPhone Shortcut → `POST http://<pi>:8080/companion`. Config: `[companion] server_host/server_port`.

**Deployed on the Pi (`dailypoem.local`, user `pi`, repo `/home/pi/daily-poem`).** All three units installed and enabled on boot: `daily-companion.timer` (01:00), `daily-companion-server.service` (:8080), alongside the existing `daily-poem.timer` (06:00). `ANTHROPIC_API_KEY` added to `/home/pi/daily-poem.env` (mode 600). Verified end-to-end on hardware: the overnight selection runs from the live Notion poem, and `POST /companion` pushed a text companion (page 2) to the panel successfully. Bug fixed during deploy: the rank model prefaces its JSON with prose, which crashed `json.loads`; parsing now extracts the `{...}` object (commit 16dac6f).

*Render-quality fixes made along the way:* `gate` now keeps clean RGB (resized to 800px) and quantizes only a probe copy for the mud test, so page 2 quantizes exactly **once** (no double-dither); `compose_companion` returns a `Render` and flows through the existing `output()` device seam; page-2 text (lens + attribution) wraps to width via `render.layout._wrap` and the image fits preserving aspect ratio. Verified: `out/companion-page2.png` lays out correctly.

**Still to build / open:**
- **Render-gate calibration** (the deferred mud-detector rework) — best done against real dithered output on the panel, since the Mac preview only approximates Spectra-6. Even bright painterly work (Bruegel) shows heavy red/green dither noise in the preview; the panel is the honest test.
- **Candidate-pool thinness** — distill should emit *searchable* terms alongside poetic angles; bias image queries toward prints/woodcuts.
- `companion/base.py` + `noop.py` are now orphaned (pipeline uses `ChosenCompanion`); harmless, worth deleting in a cleanup pass.

---

## 10. Decisions — resolved June 2026

- **LLM provider** — Anthropic directly (Claude). No provider abstraction; the GoBot pattern is not reused. Lean on Claude's literary prose quality for the rank+lens call.
- **Museum APIs** — all three: Met (no key), Art Institute of Chicago (no key), Rijksmuseum (free key — get at rijksmuseum.nl/en/research/conduct-your-research/data/api). Start keyless, add Rijksmuseum key to `.env` when ready.
- **Image pipeline storage** — `out/companion.png` (palette-quantized, 800×480) + `out/companion.json` sidecar (lens, source attribution, buried question, type). Written overnight, read on button press. Matches the existing `out/preview.png` pattern.
- **Empty-state behavior** — show the buried question alone on a full-bleed second page. One sentence, large type. A null companion is not a failure; the named question is itself a revelation.
- **Button / trigger mechanism** — iPhone Shortcut → `POST /companion` HTTP endpoint on the Pi (small HTTP server, local network). One tap on the home screen reveals the companion page. Physical Inky buttons (GPIO) are an option but fiddly if the frame is mounted.
- **Remaining open:** how the poem is passed in from `content/` (title + metadata available — see `Poem` dataclass); politeness to sources (one run/day, trivial volume, basic `User-Agent` header sufficient).

---

## 11. Working-mode note

Claude Code builds the **engine and plumbing**. The **editorial voice** — the prompts in §8 and the curatorial taste behind them — is iterated separately, by reading and tuning language, and dropped in as versioned text. Don't bake editorial logic into code; keep it in the prompt files where it can be revised without touching the pipeline.
