# The companion button (hardware)

A battery-powered Wi-Fi button that flips the frame between the poem and its
companion — no phone required. It sleeps at microamps until pressed; on a press it
wakes, sends one HTTP request to the frame, blinks a confirmation, and sleeps again.

It talks to the frame's existing button server:

```
POST http://dailypoem.local:8080/toggle
```

`/toggle` flips to whichever page is *not* currently showing, so the device stays
dead simple: one button, one request, stateless. All the state lives on the frame.

## What the button actually has to do (judge any substitute by this)

1. Join your 2.4 GHz Wi-Fi (same network as the frame).
2. Send one HTTP `POST` to the frame on a button press.
3. Deep-sleep in microamps between presses and wake on the button (for battery life).
4. Charge a small LiPo over USB-C (so you never open the enclosure).

Any board that does these works. The request itself is **already verified against
the live frame** — see "Verified" below — so the electronics are the only variable.

## Recommended parts (~$15–20)

| Part | Pick | Notes |
|---|---|---|
| Board | **Seeed Studio XIAO ESP32-C3** (~$5) | 21 × 17.5 mm. Wi-Fi, USB-C, onboard LiPo charging, µA deep sleep. The RISC-V **C3** is the low-power one — not the S3/S2. |
| Battery | **3.7 V LiPo, 300–500 mAh, with protection circuit** | Soldered to the board's `BAT+` / `BAT-` pads. 400 mAh ≈ many months on a few presses/day. |
| Button | Any **momentary SPST** push button | A 12 mm panel-mount feels nice; a 6 mm tactile is smallest. Two wires: GPIO ↔ GND. |
| Cable | USB-C | Flashing + charging. |
| Enclosure (optional) | 3D print or small project box | Interior ~40 × 40 × 15 mm is plenty. |
| Confirm LED (optional) | Any LED + ~330 Ω resistor | Blinks "sent." The XIAO C3 has no reliable user LED, so use an external one. |

### Gotchas that cause "wrong hardware" — read before buying

- **The XIAO ESP32-C3 needs its external antenna plugged in** (the little u.FL/IPEX
  antenna in the box). Without it, Wi-Fi barely reaches across a room.
- **The battery solders to pads (`BAT+`/`BAT-`), not a connector.** Polarity is
  critical — reversing it can kill the board. If you'd rather *plug in* a battery,
  buy a board with a JST-PH connector instead (see the easier alternative).
- **Get a LiPo with a protection circuit.** Most hobby cells include one; confirm it.

### Easier alternative (slightly bigger, less soldering)

An **Adafruit ESP32 Feather** (or QT Py ESP32) has a **JST LiPo connector** (battery
just plugs in) and a **PCB antenna** (no antenna to attach) — it sidesteps both
gotchas above. The trade-off is size: a Feather is ~50 × 23 mm (the "slim box"
form factor rather than the coin-cell puck).

## Wiring

- **Button:** one leg → a GPIO (default `GPIO3`), other leg → `GND`. The firmware
  enables the internal pull-up, so a press pulls the pin low.
- **Battery:** LiPo `+` → `BAT+`, `−` → `BAT-`. Double-check polarity.
- **Optional LED:** GPIO → resistor → LED → GND.

## Firmware

Two options in this folder — same behavior, pick your comfort level:

- **`esphome-button.yaml`** — declarative, ~20 lines, robust over-the-air updates.
  Flash with the ESPHome dashboard/CLI. Recommended.
- **`main.py`** — MicroPython, explicit and self-contained. Flash MicroPython, copy
  this as `main.py` with Thonny. Easiest to read and tweak.

Fill in your Wi-Fi credentials (and the frame URL if the hostname differs). Both are
**starting points** — verify the board id and the deep-sleep wake-pin line against
current docs for your exact board when you flash. The HTTP contract they rely on is
what's already proven.

## Verified

The frame side is done and tested on the real hardware: hitting
`POST /toggle` repeatedly flips the panel poem → companion → poem, with the frame
tracking which page is up (`out/current_page`). So a button that sends that one
request will work — that's the whole point of testing it before you buy.
