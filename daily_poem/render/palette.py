"""Spectra-6 palette + quantization that mirrors the inky library exactly.

The panel shows 6 inks. The library blends a *saturated* (true measured ink
colour) and *desaturated* (pure RGB) palette by a `saturation` knob, then
Floyd-Steinberg dithers against it. We reproduce that here so a Mac preview
matches what the panel is sent — and, crucially, we quantize ONCE here so the
device layer can hand the panel a ready-made 6-colour image (the library then
ships our pixels verbatim instead of re-dithering them).

Two render targets share one dither pattern:
  - preview  : recoloured with the *blended* palette so the PNG looks like e-ink.
  - hardware : recoloured with the *desaturated* (pure) palette so the library's
               re-quantization is an exact-match no-op.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

# Canonical visible-colour order. Hardware uses non-contiguous codes (index 4 is
# skipped on the panel); this remap is applied at push time, not here.
NAMES = ("black", "white", "yellow", "red", "blue", "green")


@dataclass(frozen=True)
class Spectra6:
    desaturated: list[list[int]]
    saturated: list[list[int]]
    hardware_remap: list[int]

    @classmethod
    def load(cls, path: str | Path) -> "Spectra6":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            desaturated=[list(c) for c in data["desaturated"]],
            saturated=[list(c) for c in data["saturated"]],
            hardware_remap=list(data["hardware_remap"]),
        )

    def blend(self, saturation: float) -> list[list[int]]:
        """The 6 quantize colours at a given saturation. int() truncation matches
        inky_e673._palette_blend byte-for-byte."""
        out = []
        for sat, des in zip(self.saturated, self.desaturated):
            out.append([int(s * saturation + d * (1.0 - saturation)) for s, d in zip(sat, des)])
        return out


def _palette_image(colours: list[list[int]]) -> Image.Image:
    """A 'P'-mode image carrying `colours` as its palette (padded to 256)."""
    flat: list[int] = []
    for c in colours:
        flat.extend(c)
    flat.extend([0, 0, 0] * (256 - len(colours)))
    pimg = Image.new("P", (1, 1))
    pimg.putpalette(flat)
    return pimg


def quantize(rgb: Image.Image, panel: Spectra6, saturation: float, mode: str) -> Image.Image:
    """Quantize an RGB composition to the panel's inks with Floyd-Steinberg.

    Returns a 'P' image whose palette is the 6 canonical colours in NAMES order
    (so the hardware remap lines up), with only the `mode`-permitted inks used.

      mode='mono'  -> black + white only: crisp text, no colour fringing on serifs.
      mode='full'  -> all 6 inks: for colour companion art later.
    """
    blended = panel.blend(saturation)
    allowed = [0, 1] if mode == "mono" else list(range(6))

    # Dither DECISION palette. Mono dithers against PURE black/white: the blended
    # grey "white" point ([208,209,210]) sets a bright threshold that thins serif
    # strokes toward the paper and washes the text out. Colour mode dithers against
    # the blended inks (what the panel actually shows).
    decision = panel.desaturated if mode == "mono" else blended
    quant = rgb.convert("RGB").quantize(
        colors=len(allowed),
        palette=_palette_image([decision[i] for i in allowed]),
        dither=Image.Dither.FLOYDSTEINBERG,
    )
    # `quant` indexes into `allowed`; lift it back to canonical 0..5 indices.
    lift = bytes(allowed) + bytes(256 - len(allowed))
    canonical = quant.point(lift)
    canonical.putpalette(_palette_image(blended).getpalette())
    return canonical


def to_preview_rgb(canonical: Image.Image, panel: Spectra6, saturation: float) -> Image.Image:
    """Recolour with the blended palette -> what the panel roughly looks like."""
    img = canonical.copy()
    img.putpalette(_palette_image(panel.blend(saturation)).getpalette())
    return img.convert("RGB")


def to_hardware_rgb(canonical: Image.Image, panel: Spectra6) -> Image.Image:
    """Recolour with pure inks so inky's re-quantization is an exact-match no-op."""
    img = canonical.copy()
    img.putpalette(_palette_image(panel.desaturated).getpalette())
    return img.convert("RGB")
