#!/usr/bin/env python3
"""Upload a full-screen (854x480) boot/background picture with the LOG command.

usage: set_boot.py [image] [--fit cover|contain] [--save preview.png]
Without an image an orientation test card is generated.
"""
import argparse
import os
import select
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from PIL import Image, ImageDraw, ImageFont, ImageOps

from streamdock import BG_SIZE, StreamDock

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"


def test_card():
    w, h = BG_SIZE
    img = Image.linear_gradient("L").resize((w, h)).convert("RGB")
    img = Image.merge("RGB", (img.getchannel(0), Image.new("L", (w, h), 60), ImageOps.invert(img.getchannel(0))))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, h - 1], outline="white", width=6)
    big = ImageFont.truetype(FONT, 72)
    small = ImageFont.truetype(FONT, 28)
    d.text((w / 2, h / 2), "HELLO LINUX", font=big, fill="white", anchor="mm", stroke_width=4, stroke_fill="black")
    for text, xy, anchor in (("TL", (14, 10), "la"), ("TR", (w - 14, 10), "ra"),
                             ("BL", (14, h - 10), "ld"), ("BR", (w - 14, h - 10), "rd")):
        d.text(xy, text, font=small, fill="yellow", anchor=anchor, stroke_width=2, stroke_fill="black")
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image", nargs="?")
    ap.add_argument("--fit", choices=("cover", "contain"), default="cover")
    ap.add_argument("--save", help="also write the final 854x480 picture here")
    args = ap.parse_args()

    if args.image:
        src = Image.open(args.image).convert("RGBA")
        src = Image.alpha_composite(Image.new("RGBA", src.size, "black"), src).convert("RGB")
        if args.fit == "cover":
            img = ImageOps.fit(src, BG_SIZE, Image.LANCZOS)
        else:
            img = ImageOps.pad(src, BG_SIZE, Image.LANCZOS, color="black")
    else:
        img = test_card()
    if args.save:
        img.save(args.save)

    with StreamDock(heartbeat=False) as dock:
        # Drain any stale input reports so we only see the LOG acknowledgement.
        while select.select([dock.fd], [], [], 0)[0]:
            os.read(dock.fd, 1024)
        t0 = time.time()
        dock.set_background(img)  # includes the 1.4 s settle time
        r, _, _ = select.select([dock.fd], [], [], 5)
        if r:
            data = os.read(dock.fd, 1024)
            print(f"ack after {time.time() - t0:.1f}s: {data.rstrip(bytes(1))[:16]!r}")
        else:
            print("no acknowledgement within 5 s")
        dock.refresh()


if __name__ == "__main__":
    main()
