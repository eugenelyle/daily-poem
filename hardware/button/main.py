# Companion button — MicroPython for an ESP32-C3 (e.g. Seeed XIAO ESP32-C3).
#
# Flash MicroPython to the board, then copy this file as `main.py` (Thonny works).
# On each wake: join Wi-Fi, POST to the frame's /toggle, blink to confirm, deep-sleep
# until the button pulls the pin low again.
#
# Fill in WIFI_SSID / WIFI_PASS below. FRAME_URL matches the frame's button server.

import time
import network
import machine
from machine import Pin, deepsleep

try:
    import urequests as requests
except ImportError:
    import requests

WIFI_SSID = "YOUR_WIFI"
WIFI_PASS = "YOUR_PASSWORD"
FRAME_URL = "http://dailypoem.local:8080/toggle"
BUTTON_PIN = 3          # GPIO the button pulls to GND
LED_PIN = 4             # optional external LED (GPIO -> resistor -> LED -> GND); set None to skip

_led = Pin(LED_PIN, Pin.OUT) if LED_PIN is not None else None


def blink(n):
    if _led is None:
        return
    for _ in range(n):
        _led.on(); time.sleep_ms(70); _led.off(); time.sleep_ms(90)


def connect(timeout_ms=10000):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASS)
        t0 = time.ticks_ms()
        while not wlan.isconnected():
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
                return False
            time.sleep_ms(100)
    return True


def toggle():
    try:
        r = requests.post(FRAME_URL)
        r.close()
        return True
    except Exception:
        return False


# --- on wake: connect, flip the frame, confirm --------------------------------
ok = connect() and toggle()
blink(2 if ok else 5)   # 2 = sent, 5 = something failed

# --- arm the button as the wake source, then sleep at µA ----------------------
# NOTE: deep-sleep GPIO wake on the ESP32-C3 differs from the classic ESP32. Verify
# this line for your MicroPython build — some C3 builds use esp32.wake_on_ext1, and
# a few need machine.Pin wake configured differently. The rest of the script is portable.
try:
    import esp32
    _wake = Pin(BUTTON_PIN, Pin.IN, Pin.PULL_UP)
    esp32.wake_on_ext0(pin=_wake, level=esp32.WAKEUP_ALL_LOW)
except Exception:
    pass

deepsleep()             # wakes on the button; re-runs this script from the top
