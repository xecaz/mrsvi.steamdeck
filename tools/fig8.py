#!/usr/bin/env python3
"""Scroll a large image across the 15 keys and the side strip along a figure-8 (Lissajous 1:2) path.

usage: fig8.py [image] [--height H | --zoom Z] [--period SECONDS] [--quality Q] [--duration SECONDS]
Without an image a procedural test pattern is generated.
"""
import argparse
import math
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageOps

from panel import VIEW_H, VIEW_W, screen_rects
from streamdock import StreamDock, encode_jpeg

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def test_pattern(w=2400, h=1400):
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    v = np.sin(x / 90) + np.sin(y / 70) + np.sin((x + y) / 130) + np.sin(np.hypot(x - w / 2, y - h / 2) / 60)
    rgb = np.stack([128 + 127 * np.sin(v * np.pi + p) for p in (0, 2.1, 4.2)], axis=-1)
    img = Image.fromarray(rgb.astype(np.uint8))
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(FONT, 160)
    d.text((w / 2, h / 2), "MIRABOX", font=font, fill="white", anchor="mm", stroke_width=8, stroke_fill="black")
    for gx in range(0, w, 200):
        d.line([(gx, 0), (gx, h)], fill=(0, 0, 0), width=3)
    for gy in range(0, h, 200):
        d.line([(0, gy), (w, gy)], fill=(0, 0, 0), width=3)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?")
    ap.add_argument("--period", type=float, default=12.0, help="seconds per full figure-8")
    ap.add_argument("--quality", type=int, default=80)
    ap.add_argument("--duration", type=float, default=0, help="stop after N seconds (0 = forever)")
    ap.add_argument("--zoom", type=float, default=1.0, help="scale the image up for a bigger figure-8")
    ap.add_argument("--height", type=float, help="image height as a multiple of the deck's height (overrides --zoom)")
    args = ap.parse_args()

    if args.image:
        src = Image.open(args.image).convert("RGBA")
        src = Image.alpha_composite(Image.new("RGBA", src.size, "black"), src).convert("RGB")
    else:
        src = test_pattern()
    if args.height:
        # Scale the image to a fixed multiple of the deck's height, then pad with black so the
        # figure-8 always has room to move even when the image is barely wider than the deck.
        scale = args.height * VIEW_H / src.height
        src = src.resize((int(src.width * scale), int(src.height * scale)), Image.LANCZOS)
        ax = max((src.width - VIEW_W) / 2, 0.3 * VIEW_W)
        ay = max((src.height - VIEW_H) / 2, 0.3 * VIEW_H)
        src = ImageOps.pad(src, (int(VIEW_W + 2 * ax), int(VIEW_H + 2 * ay)), color="black")
    else:
        # Make sure the source is comfortably larger than the viewport.
        scale = args.zoom * max(1.0, 2.0 * VIEW_W / src.width, 2.0 * VIEW_H / src.height)
        if scale > 1:
            src = src.resize((int(src.width * scale), int(src.height * scale)), Image.LANCZOS)
        ax = (src.width - VIEW_W) / 2
        ay = (src.height - VIEW_H) / 2
    wins = list(screen_rects().items())
    pool = ThreadPoolExecutor()

    with StreamDock() as dock:
        t0 = time.time()
        frames = 0
        last = t0
        try:
            while not args.duration or time.time() - t0 < args.duration:
                t = 2 * math.pi * (time.time() - t0) / args.period
                ox = ax + ax * math.sin(t)
                oy = ay + ay * math.sin(2 * t)

                def enc(w):
                    idx, ((x, y, cw, ch), out) = w
                    left, top = int(ox + x), int(oy + y)
                    return idx, encode_jpeg(src.crop((left, top, left + cw, top + ch)), out, args.quality)

                for idx, jpeg in pool.map(enc, wins):
                    dock.set_key_jpeg(idx, jpeg)
                dock.refresh()
                frames += 1
                now = time.time()
                if now - last >= 2:
                    print(f"{frames / (now - last):.1f} fps", flush=True)
                    frames, last = 0, now
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
