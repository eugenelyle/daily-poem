"""Raspberry Pi target: push the render to the physical Inky panel.

`inky` is imported lazily inside push() so importing this module never drags in
Pi-only native deps on a Mac. Reached only when target == "inky".

We hand the panel a pre-quantized image recoloured with the *pure* inks, so the
library's internal re-quantization is an exact-match no-op — our dithering (done
once in render/) is what reaches the panel.
"""
from __future__ import annotations

from ..config import Config
from ..render import palette as pal
from ..render.compose import Render


def push(render: Render, cfg: Config) -> None:
    from inky.auto import auto  # noqa: PLC0415 — lazy: Pi-only import

    inky = auto()  # auto-detect the connected panel via its EEPROM

    hw = pal.to_hardware_rgb(render.canonical, render.panel)
    if cfg.page.rotate_for_panel:
        hw = hw.rotate(-cfg.page.rotate_for_panel, expand=True)  # clockwise

    if hw.size != (inky.width, inky.height):
        raise ValueError(
            f"Rotated image {hw.size} != panel {(inky.width, inky.height)}; "
            "check page size and rotate_for_panel."
        )

    inky.set_image(hw, saturation=cfg.palette.saturation)
    inky.show()
