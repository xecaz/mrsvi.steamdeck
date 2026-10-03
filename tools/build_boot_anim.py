#!/usr/bin/env python3
"""Build a data partition (and a flashable .img) holding a figure-8 boot animation.

usage: build_boot_anim.py STOCK.img IMAGE [--out DIR] [--fig8 N] [--zoom N] [--height H] [--quality Q]

Writes into DIR (default fw/out):
  data_anim.lfs         the new 5 MB littlefs data partition
  <stock>-anim.img      STOCK.img with that data partition and its META CRC replaced
  preview.gif           the frames as stored
  preview_deck.gif      the frames as seen through the deck's key windows and strip

The data partition keeps the stock files, sets logo_jpg_dir/test_logo.jpg to IMAGE (the
static boot picture) and adds logo_jpg_dir/f00.jpg.. with one figure-8 over IMAGE followed by
a zoom out that lands exactly on the static picture. The stock firmware ignores the extra
files; playing them needs a patched OS.

Requires littlefs-python (pip install littlefs-python).
"""
import argparse
import io
import math
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import littlefs
from PIL import Image, ImageDraw, ImageOps

from streamdock import BG_SIZE, encode_jpeg

# Geometry of the stock data partition (superblock + commit padding of the vendor image).
BLOCK_SIZE = 4096
BLOCK_COUNT = 1280
PROG_SIZE = 64
DISK_VERSION = 0x00020000
NAME_MAX = 32  # the firmware's littlefs rejects a larger name_max
LOGO_DIR = "/logo_jpg_dir"

PANEL_W, PANEL_H = BG_SIZE

# Key windows on the panel (centres and size from the coordinate-grid photo) and the strip.
WINDOW = 100
KEY_CX = [65.6 + 153.5 * c for c in range(5)]
KEY_CY = [85.5 + 152.5 * r for r in range(3)]
STRIP = (768, 30, 854, 452)


def parse_img(data):
    """{name: (meta_offset, data_offset, size)} for every component of an AIC.FW image."""
    if data[:6] != b"AIC.FW":
        raise ValueError("not an AIC.FW image")
    meta_off, meta_size = struct.unpack("<2I", data[332:340])
    parts = {}
    for i in range(meta_size // 512):
        m = meta_off + 512 * i
        name = data[m + 8:m + 72].split(b"\0")[0].decode()
        off, size = struct.unpack("<2I", data[m + 136:m + 144])
        parts[name] = (m, off, size)
    return parts


def open_lfs(buf=None):
    fs = littlefs.LittleFS(block_size=BLOCK_SIZE, block_count=BLOCK_COUNT, prog_size=PROG_SIZE,
                           read_size=PROG_SIZE, name_max=NAME_MAX, disk_version=DISK_VERSION,
                           mount=buf is None)
    if buf is not None:
        fs.context.buffer = bytearray(buf)
        fs.mount()
    return fs


def read_all(fs):
    files = {}
    for root, _, names in fs.walk("/"):
        for n in names:
            path = root.rstrip("/") + "/" + n
            with fs.open(path, "rb") as f:
                files[path] = f.read()
    return files


def render_frames(face, n_fig8, n_zoom, height):
    """Panel-sized RGB frames: one figure-8 at `height` x panel height, then a zoom out to 1x."""
    frames = []
    big = face.resize((round(face.width * height * PANEL_H / face.height), round(height * PANEL_H)), Image.LANCZOS)
    ax = max((big.width - PANEL_W) / 2, 0.3 * PANEL_W)
    ay = max((big.height - PANEL_H) / 2, 0.3 * PANEL_H)
    canvas = ImageOps.pad(big, (round(PANEL_W + 2 * ax), round(PANEL_H + 2 * ay)), color="black")
    for i in range(n_fig8):
        t = 2 * math.pi * i / n_fig8
        ox, oy = ax + ax * math.sin(t), ay + ay * math.sin(2 * t)
        frames.append(canvas.crop((round(ox), round(oy), round(ox) + PANEL_W, round(oy) + PANEL_H)))
    for k in range(1, n_zoom + 1):
        s = k / n_zoom
        z = height + (1 - height) * (1 - (1 - s) ** 2)  # ease out
        scaled = face.resize((round(face.width * z * PANEL_H / face.height), round(z * PANEL_H)), Image.LANCZOS)
        frame = Image.new("RGB", (PANEL_W, PANEL_H), "black")
        frame.paste(scaled, ((PANEL_W - scaled.width) // 2, (PANEL_H - scaled.height) // 2))
        frames.append(frame)
    return frames


def deck_view(frame):
    """What the panel frame looks like through the faceplate."""
    mask = Image.new("L", (PANEL_W, PANEL_H), 0)
    d = ImageDraw.Draw(mask)
    for cx in KEY_CX:
        for cy in KEY_CY:
            d.rectangle([cx - WINDOW / 2, cy - WINDOW / 2, cx + WINDOW / 2, cy + WINDOW / 2], fill=255)
    d.rectangle(STRIP, fill=255)
    return Image.composite(frame, Image.new("RGB", frame.size, (25, 25, 25)), mask)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stock_img")
    ap.add_argument("image")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "fw", "out"))
    ap.add_argument("--fig8", type=int, default=60, help="frames for the figure-8")
    ap.add_argument("--zoom", type=int, default=15, help="frames for the zoom out")
    ap.add_argument("--height", type=float, default=1.9, help="face height during the figure-8, x panel height")
    ap.add_argument("--quality", type=int, default=75)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)

    img = open(args.stock_img, "rb").read()
    parts = parse_img(img)
    meta, off, size = parts["image.target.data"]
    if size != BLOCK_SIZE * BLOCK_COUNT:
        raise SystemExit(f"unexpected data partition size {size}")

    stock_files = read_all(open_lfs(img[off:off + size]))
    print(f"stock data partition: {len(stock_files)} files")

    src = Image.open(args.image).convert("RGBA")
    face = Image.alpha_composite(Image.new("RGBA", src.size, "black"), src).convert("RGB")
    logo = ImageOps.pad(face, BG_SIZE, Image.LANCZOS, color="black")
    frames = render_frames(face, args.fig8, args.zoom, args.height)

    files = dict(stock_files)
    files[f"{LOGO_DIR}/test_logo.jpg"] = encode_jpeg(logo, BG_SIZE, 85)
    jpegs = [encode_jpeg(f, BG_SIZE, args.quality) for f in frames]
    for i, j in enumerate(jpegs):
        files[f"{LOGO_DIR}/f{i:02d}.jpg"] = j
    print(f"{len(jpegs)} frames, {sum(map(len, jpegs)) / 1e6:.2f} MB, largest {max(map(len, jpegs)) / 1e3:.0f} KB")

    fs = open_lfs()
    for path in sorted(files):
        d = os.path.dirname(path)
        if d != "/":
            try:
                fs.makedirs(d, exist_ok=True)
            except FileExistsError:
                pass
        with fs.open(path, "wb") as f:
            f.write(files[path])
    print(f"littlefs: {fs.used_block_count} of {BLOCK_COUNT} blocks used")
    fs.unmount()
    data = bytes(fs.context.buffer)

    # Verify: remount from bytes and compare every file.
    if read_all(open_lfs(data)) != files:
        raise SystemExit("verification failed: remounted files differ")
    # Superblock fields must match the stock partition exactly.
    def superblock(buf):
        i = buf.find(b"littlefs", 0, BLOCK_SIZE)
        return struct.unpack("<6I", buf[i + 12:i + 36])
    if superblock(data) != superblock(img[off:off + size]):
        raise SystemExit(f"verification failed: superblock {superblock(data)} != stock {superblock(img[off:off + size])}")
    print("verified: remount matches, superblock identical to stock")

    with open(os.path.join(args.out, "data_anim.lfs"), "wb") as f:
        f.write(data)
    new = bytearray(img)
    new[off:off + size] = data
    struct.pack_into("<I", new, meta + 144, zlib.crc32(data))
    name = os.path.splitext(os.path.basename(args.stock_img))[0] + "-anim.img"
    with open(os.path.join(args.out, name), "wb") as f:
        f.write(new)
    print(f"wrote {name}: data CRC {zlib.crc32(data):#010x}")

    # Previews: decode the stored JPEGs (rotated back) so they show exactly what is on flash.
    shown = [Image.open(io.BytesIO(j)).rotate(-90, expand=True) for j in jpegs]
    shown += [ImageOps.pad(face, BG_SIZE, color="black")] * 12  # hold the static logo a moment
    for fname, imgs in (("preview.gif", shown), ("preview_deck.gif", [deck_view(s) for s in shown])):
        small = [i.resize((PANEL_W // 2, PANEL_H // 2)) for i in imgs]
        small[0].save(os.path.join(args.out, fname), save_all=True, append_images=small[1:],
                      duration=40, loop=0)
    print(f"previews in {args.out}")


if __name__ == "__main__":
    main()
