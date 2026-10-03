#!/usr/bin/env python3
"""Fill the right-hand strip with three slices (slots 16, 17, 18), each starting at its own slot.

usage: strip_split_test.py [H16 H17 H18] [SECONDS]
Each slice shows five colour columns, its slot number and a white tick every 20 px, so a photo
shows whether each slice is decoded completely and where it lands.
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image, ImageDraw, ImageFont

from streamdock import StreamDock, encode_jpeg

heights = [int(a) for a in sys.argv[1:4]] if len(sys.argv) > 3 else [152, 152, 120]
hold = float(sys.argv[4]) if len(sys.argv) > 4 else 600
big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
colours = ["red", "orange", "yellow", "green", "cyan"]

with StreamDock() as dock:
    for slot, h in zip((16, 17, 18), heights):
        img = Image.new("RGB", (80, h))
        d = ImageDraw.Draw(img)
        for i, x in enumerate(range(0, 80, 16)):
            d.rectangle([x, 0, x + 15, h - 1], fill=colours[i])
        for y in range(0, h, 20):
            d.line([(0, y), (79, y)], fill="white", width=2)
        d.text((40, 30), str(slot), font=big, fill="black", anchor="mm")
        dock.set_key_jpeg(slot, encode_jpeg(img, (80, h)))
    dock.refresh()
    print(f"slices sent: {heights}", flush=True)
    time.sleep(hold)
