#!/usr/bin/env python3
"""Show labelled horizontal stripes across the whole layout (keys + strip) using panel.py.

If panel.py is right, stripes and their y labels line up between neighbouring screens.
usage: layout_test.py [SECONDS]
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image, ImageDraw, ImageFont

from panel import VIEW_H, VIEW_W, screen_rects
from streamdock import StreamDock, encode_jpeg

font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
colours = [(200, 40, 40), (230, 150, 0), (40, 160, 40), (30, 110, 220), (150, 60, 200)]

img = Image.new("RGB", (VIEW_W, VIEW_H))
d = ImageDraw.Draw(img)
for i, y in enumerate(range(0, VIEW_H, 20)):
    d.rectangle([0, y, VIEW_W, y + 19], fill=colours[i % len(colours)])
    d.line([(0, y), (VIEW_W, y)], fill="white", width=1)
    # Label every stripe in every column so each screen shows its own numbers.
    for x in range(4, VIEW_W, 48):
        d.text((x, y + 10), str(y), font=font, fill="white", anchor="lm")

hold = float(sys.argv[1]) if len(sys.argv) > 1 else 300
with StreamDock() as dock:
    for idx, ((x, y, w, h), out) in screen_rects().items():
        dock.set_key_jpeg(idx, encode_jpeg(img.crop((x, y, x + w, y + h)), out))
    dock.refresh()
    print("layout test shown", flush=True)
    time.sleep(hold)
