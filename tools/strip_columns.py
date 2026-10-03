#!/usr/bin/env python3
"""Probe the strip horizontally: send slot 16 a WIDTH x HEIGHT image of numbered 16 px columns.

usage: strip_columns.py [WIDTH] [HEIGHT] [SECONDS]
The columns that show up (and where) tell where the firmware draws the image and how wide.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image, ImageDraw, ImageFont

from streamdock import StreamDock, encode_jpeg

w = int(sys.argv[1]) if len(sys.argv) > 1 else 160
h = int(sys.argv[2]) if len(sys.argv) > 2 else 440
hold = float(sys.argv[3]) if len(sys.argv) > 3 else 600
font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 14)
colours = ["red", "orange", "yellow", "green", "cyan", "blue", "magenta", "white", "gray", "brown"]

img = Image.new("RGB", (w, h))
d = ImageDraw.Draw(img)
for i, x in enumerate(range(0, w, 16)):
    d.rectangle([x, 0, x + 15, h - 1], fill=colours[i % len(colours)])
    for y in range(10, h, 40):
        d.text((x + 8, y), str(i % 10), font=font, fill="black", anchor="mm")

with StreamDock() as dock:
    dock.set_key_jpeg(16, encode_jpeg(img, (w, h)))
    dock.refresh()
    print(f"sent {w}x{h} columns to slot 16", flush=True)
    time.sleep(hold)
