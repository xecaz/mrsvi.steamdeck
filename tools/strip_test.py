#!/usr/bin/env python3
"""Probe the right-hand strip: send one key slot an image of arbitrary size.

usage: strip_test.py INDEX WIDTH HEIGHT [SECONDS]
The image has a colour band every 50 px with its y value written in it, so a photo shows
how much of it the firmware draws and where.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image, ImageDraw, ImageFont

from streamdock import StreamDock, encode_jpeg

index, w, h = (int(a) for a in sys.argv[1:4])
hold = float(sys.argv[4]) if len(sys.argv) > 4 else 300
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 16)
colours = ["red", "orange", "yellow", "green", "cyan", "blue", "magenta", "white", "gray"]

img = Image.new("RGB", (w, h))
d = ImageDraw.Draw(img)
for i, y in enumerate(range(0, h, 50)):
    d.rectangle([0, y, w - 1, y + 49], fill=colours[i % len(colours)])
    d.text((w / 2, y + 25), str(y), font=font, fill="black", anchor="mm")
d.rectangle([0, 0, w - 1, h - 1], outline="white", width=2)

with StreamDock() as dock:
    dock.set_key_jpeg(index, encode_jpeg(img, (w, h)))
    dock.refresh()
    print(f"sent {w}x{h} to key {index}", flush=True)
    time.sleep(hold)
