#!/usr/bin/env python3
"""Draw each screen's hardware index on it, then log key presses for a while."""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image, ImageDraw, ImageFont

from streamdock import SIDE_SIZE, KEY_SIZE, StreamDock, key_position

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def tile(index):
    size = SIDE_SIZE if index > 15 else KEY_SIZE
    hue = (index * 37) % 360
    img = Image.new("HSV", (size, size), (hue * 255 // 360, 200, 160)).convert("RGB")
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, size // 2)
    d.text((size / 2, size / 2), str(index), font=font, fill="white", anchor="mm")
    d.polygon([(0, 0), (size // 4, 0), (0, size // 4)], fill="white")  # top-left marker
    return img


duration = float(sys.argv[1]) if len(sys.argv) > 1 else 40
with StreamDock() as dock:
    print("device", dock.path, flush=True)
    for i in range(1, 19):
        dock.set_key_image(i, tile(i))
    dock.refresh()
    print("images sent; press keys", flush=True)
    end = time.time() + duration
    while time.time() < end:
        ev = dock.read_event(0.5)
        if ev:
            idx, pressed = ev
            print(f"key {idx:2d} pos(col,row)={key_position(idx)} {'down' if pressed else 'up'}", flush=True)
